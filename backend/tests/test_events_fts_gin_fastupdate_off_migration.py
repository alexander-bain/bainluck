"""#10090: `events_fts_gin_fastupdate_off` covers the two GIN indexes no migration creates.

THE SHIP. A live score or price write on `events` never stops for seconds to
merge a search index's backlog inside its own statement.

These are the shape guards that run without a database. The behaviour gate is
`tests/integration/test_events_writes_never_merge_a_gin_backlog_10090_pg.py`.
Its census reads every `events` GIN from `pg_index` after both revisions and
requires `fastupdate=off` on each one.

Pins:
* together with its parent, the migration names every GIN index production's
  `events` carries (read 2026-10-29 19:45Z), and no index twice;
* it chains on the parent and is the single head;
* both batches open with `LOCK TABLE events IN ACCESS EXCLUSIVE MODE`;
* each ALTER is `ALTER INDEX IF EXISTS … SET (fastupdate = off)`, because a
  database built from migrations alone does not have these indexes;
* the downgrade resets `fastupdate` only, on these two only;
* the script never commits mid-batch, so `alembic/env.py` keeps its lock retry;
* the table lock is requested only at a quiet moment, never when there is
  nothing to change, and a run that finds no quiet moment ends inside the
  release-phase budget with an error env.py does not retry (v5958);
* every gate read follows a fresh `pg_stat_activity` copy, and an ALTER that
  times out holding the table ends as that same unretried error (#11757 review).
"""

from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory

import pytest

from app.utils.migration_lock_budget import RELEASE_PHASE_BUDGET_S, batch_is_retryable
from app.utils.repair_lock_budget import is_lock_timeout

BACKEND = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
NAME = "events_fts_gin_fastupdate_off"
PARENT = "events_gin_fastupdate_off"
SOURCE = (VERSIONS / f"{NAME}.py").read_text(encoding="utf-8")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load(NAME)
PARENT_MIGRATION = _load(PARENT)

LOCK_EVENTS = "LOCK TABLE events IN ACCESS EXCLUSIVE MODE"
CLEAR = "SELECT pg_stat_clear_snapshot()"

#: Every GIN index on production's `events` (db-query, 2026-10-29 19:45Z,
#: artifacts/latency-10090-fts-gin-20261029T1945Z/idxdef.json), plus the
#: duplicate `_team_name_trgm` pair the parent still names with IF EXISTS
#: (dropped in attended psql before G2).
PRODUCTION_EVENTS_GIN = {
    "ix_events_event_tags",
    "ix_events_home_trgm",
    "ix_events_away_trgm",
    "ix_events_fts_home",
    "ix_events_fts_away",
}
DROPPED_DUPLICATES = {"ix_events_home_team_name_trgm", "ix_events_away_team_name_trgm"}


def test_revision_id_fits_gotcha_1_chains_on_the_parent_and_is_the_single_head():
    assert MIGRATION.revision == NAME
    assert len(MIGRATION.revision) <= 32
    assert MIGRATION.down_revision == PARENT
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert list(script.get_heads()) == [NAME]


def test_with_its_parent_it_names_every_production_events_gin_once():
    names = PARENT_MIGRATION.INDEXES + MIGRATION.INDEXES
    assert len(names) == len(set(names))
    assert set(names) == PRODUCTION_EVENTS_GIN | DROPPED_DUPLICATES
    assert set(MIGRATION.INDEXES) == {"ix_events_fts_home", "ix_events_fts_away"}


def test_upgrade_sets_only_fastupdate_off_after_the_table_lock():
    assert MIGRATION.UPGRADE_SQL == (LOCK_EVENTS,) + tuple(
        f"ALTER INDEX IF EXISTS {name} SET (fastupdate = off)"
        for name in MIGRATION.INDEXES
    )


def test_downgrade_resets_only_fastupdate_on_these_two():
    assert MIGRATION.DOWNGRADE_SQL == (LOCK_EVENTS,) + tuple(
        f"ALTER INDEX IF EXISTS {name} RESET (fastupdate)"
        for name in MIGRATION.INDEXES
    )
    assert all("gin_pending_list_limit" not in s for s in MIGRATION.DOWNGRADE_SQL)


class _LockNotAvailable(Exception):
    pgcode = "55P03"


class _Result:
    def __init__(self, value):
        self.value = value

    def one(self):
        return self.value

    def scalar_one(self):
        return self.value


class _Bind:
    """Answers the migration's catalogue reads from a script; records every statement."""

    def __init__(self, state, gate=(), refusals=0, alter_refusals=0):
        self.state, self.gate, self.refusals = state, list(gate), refusals
        self.alter_refusals = alter_refusals
        self.sql: list[str] = []

    def execute(self, clause, params=None):
        sql = str(clause)
        self.sql.append(sql)
        if sql == MIGRATION.STATE_SQL:
            return _Result(self.state)
        if sql == MIGRATION.GATE_SQL:
            assert params == {"age": MIGRATION.GATE_HOLDER_AGE_S}
            return _Result(self.gate.pop(0) if self.gate else 0)
        if sql == LOCK_EVENTS and self.refusals:
            self.refusals -= 1
            raise _LockNotAvailable("canceling statement due to lock timeout")
        if sql.startswith("ALTER") and self.alter_refusals:
            self.alter_refusals -= 1
            raise _LockNotAvailable("canceling statement due to lock timeout")
        return _Result(None)


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _run(monkeypatch, direction, bind, clock=None):
    clock = clock or _Clock()
    monkeypatch.setattr(MIGRATION, "op", SimpleNamespace(get_bind=lambda: bind, execute=bind.execute))
    real = MIGRATION.take_events_lock
    monkeypatch.setattr(
        MIGRATION, "take_events_lock", lambda b: real(b, sleep=clock.sleep, clock=clock)
    )
    getattr(MIGRATION, direction)()
    return clock


@pytest.mark.parametrize(
    "direction,state", [("upgrade", (2, 2)), ("upgrade", (0, 0)), ("downgrade", (0, 2))]
)
def test_nothing_to_change_takes_no_lock(monkeypatch, direction, state):
    bind = _Bind(state)
    _run(monkeypatch, direction, bind)
    assert bind.sql == [MIGRATION.STATE_SQL], (
        "an already-applied index must cost the release nothing, least of all "
        "a pending ACCESS EXCLUSIVE that every writer queues behind"
    )


@pytest.mark.parametrize("direction,state", [("upgrade", (1, 2)), ("downgrade", (2, 2))])
def test_the_lock_is_requested_only_once_no_old_holder_remains(monkeypatch, direction, state):
    bind = _Bind(state, gate=[3, 1, 0])
    clock = _run(monkeypatch, direction, bind)
    batch = MIGRATION.UPGRADE_SQL if direction == "upgrade" else MIGRATION.DOWNGRADE_SQL
    assert bind.sql == [
        MIGRATION.STATE_SQL,
        f"SET LOCAL lock_timeout = '{MIGRATION.LOCK_TRY_TIMEOUT_MS}ms'",
        CLEAR,
        MIGRATION.GATE_SQL,
        CLEAR,
        MIGRATION.GATE_SQL,
        CLEAR,
        MIGRATION.GATE_SQL,
        "SAVEPOINT events_lock",
        LOCK_EVENTS,
        "RELEASE SAVEPOINT events_lock",
        *batch[1:],
    ]
    assert clock.t == 2 * MIGRATION.GATE_POLL_S


def test_a_refused_request_is_rolled_back_and_waits_for_the_next_quiet_moment(monkeypatch):
    bind = _Bind((0, 2), gate=[0, 2, 0], refusals=1)
    _run(monkeypatch, "upgrade", bind)
    tail = bind.sql[bind.sql.index("SAVEPOINT events_lock"):]
    assert tail == [
        "SAVEPOINT events_lock",
        LOCK_EVENTS,
        "ROLLBACK TO SAVEPOINT events_lock",
        CLEAR,
        MIGRATION.GATE_SQL,
        CLEAR,
        MIGRATION.GATE_SQL,
        "SAVEPOINT events_lock",
        LOCK_EVENTS,
        "RELEASE SAVEPOINT events_lock",
        *MIGRATION.UPGRADE_SQL[1:],
    ]


def _assert_not_taken_and_not_retried(monkeypatch, bind, clock):
    with pytest.raises(MIGRATION.EventsLockNotTaken) as caught:
        _run(monkeypatch, "upgrade", bind, clock)
    assert not is_lock_timeout(caught.value), (
        "env.py retries a lock timeout up to six times, which would run the "
        "whole gate budget six times inside one release phase"
    )
    assert not any(s.startswith("ALTER") for s in bind.sql)
    return caught.value


def test_no_quiet_moment_ends_at_the_budget_without_a_request(monkeypatch):
    clock = _Clock()
    bind = _Bind((0, 2), gate=[1] * 100_000)
    _assert_not_taken_and_not_retried(monkeypatch, bind, clock)
    assert LOCK_EVENTS not in bind.sql
    gates = [i for i, s in enumerate(bind.sql) if s == MIGRATION.GATE_SQL]
    assert len(gates) > 200 and all(bind.sql[i - 1] == CLEAR for i in gates), (
        "a gate read without a fresh pg_stat_activity copy joins live locks "
        "against ages frozen at the first poll"
    )
    assert MIGRATION.GATE_BUDGET_S <= clock.t <= MIGRATION.GATE_BUDGET_S + MIGRATION.GATE_POLL_S


def test_refusals_stop_at_the_request_cap(monkeypatch):
    bind = _Bind((0, 2), refusals=100)
    _assert_not_taken_and_not_retried(monkeypatch, bind, _Clock())
    assert bind.sql.count(LOCK_EVENTS) == MIGRATION.MAX_LOCK_TRIES
    assert bind.sql.count("ROLLBACK TO SAVEPOINT events_lock") == MIGRATION.MAX_LOCK_TRIES


def test_an_alter_timing_out_holding_the_table_ends_unretried(monkeypatch):
    bind = _Bind((0, 2), alter_refusals=1)
    with pytest.raises(MIGRATION.EventsLockNotTaken) as caught:
        _run(monkeypatch, "upgrade", bind)
    assert not is_lock_timeout(caught.value), (
        "a bare 55P03 here lets env.py rerun the whole gate up to six times, "
        "past the release-phase budget"
    )
    assert bind.sql.count(LOCK_EVENTS) == 1
    assert "RELEASE SAVEPOINT events_lock" in bind.sql
    assert [s for s in bind.sql if s.startswith("ALTER")] == [MIGRATION.UPGRADE_SQL[1]]


def test_the_worst_case_fits_the_release_phase_and_each_stall_is_short():
    worst = MIGRATION.GATE_BUDGET_S + MIGRATION.MAX_LOCK_TRIES * MIGRATION.LOCK_TRY_TIMEOUT_MS / 1000
    assert worst < RELEASE_PHASE_BUDGET_S
    assert MIGRATION.LOCK_TRY_TIMEOUT_MS <= 1500
    assert MIGRATION.GATE_HOLDER_AGE_S < MIGRATION.LOCK_TRY_TIMEOUT_MS / 1000


def test_the_batch_keeps_envs_lock_retry():
    assert batch_is_retryable([SOURCE])
