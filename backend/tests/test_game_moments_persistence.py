"""THE MOMENTS ENGINE — persistence contract at the task boundary (#1445).

Every test here is a case from the C59 offline pack
(`scripts/evals/game_moments_persistence_fixtures.json`, commit 0ee2e367) lifted
onto the real `_compute_game_moments` loop: first write, idempotent rerun,
correction, authoritative empty, fetch failure, overlap, poison sibling,
rollback-safe access, cancellation.

There is no PostgreSQL harness in this suite (every other test mocks the DB), so
the fake session below does two things a mock cannot: it enforces the real
`uq_game_moment_event_key` constraint over a committed row store, and it
compiles each statement with the PostgreSQL dialect — so the ON CONFLICT target
and the advisory lock are the same SQL production emits. Cross-connection
isolation is proved by the organic beats, not here.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import game_moments as gm

_T0 = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)


class Blocked(Exception):
    """Another transaction holds this event's advisory lock."""


class UniqueViolation(Exception):
    """uq_game_moment_event_key."""


class Store:
    """Committed `game_moments` rows — what an outside reader can see."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.locks: set = set()

    def keys(self, event_id):
        return sorted(r["dedupe_key"] for r in self.rows if r["event_id"] == event_id)


class FakeSession:
    """Interprets the statements `_replace_event_moments` actually emits."""

    def __init__(self, store, events, snapshots):
        self.store = store
        self.events = events
        self.snapshots = snapshots  # event_id -> list | Exception
        self.staged = list(store.rows)
        self.held_locks: set = set()
        self.statements: list[str] = []
        self.lock_keys: list[tuple] = []
        self.fail_insert_for: set = set()

    # --- SQLAlchemy surface -------------------------------------------------
    async def execute(self, stmt):
        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        params = compiled.params
        self.statements.append(sql)
        return self._dispatch(sql, params)

    def _dispatch(self, sql, params):
        if "pg_advisory_xact_lock" in sql:
            key = (params["pg_advisory_xact_lock_2"], params["pg_advisory_xact_lock_3"])
            self.lock_keys.append(key)
            if key in self.store.locks and key not in self.held_locks:
                raise Blocked(str(key))
            self.store.locks.add(key)
            self.held_locks.add(key)
            return _Result([])
        if sql.startswith("INSERT INTO game_moments"):
            assert "ON CONFLICT ON CONSTRAINT uq_game_moment_event_key DO UPDATE" in sql
            self._upsert(self._rows_from_params(params))
            return _Result([])
        if sql.startswith("DELETE FROM game_moments"):
            keep = params.get("dedupe_key_1")
            event_id = params["event_id_1"]
            self.staged = [
                r
                for r in self.staged
                if r["event_id"] != event_id
                or (keep is not None and r["dedupe_key"] in keep)
            ]
            return _Result([])
        if "FROM win_prob_snapshots" in sql:
            got = self.snapshots.get(params.get("event_id_1"), [])
            if isinstance(got, BaseException):
                raise got
            return _Result(got)
        if "FROM events" in sql:
            return _Result(self.events)
        raise AssertionError(f"unexpected statement: {sql}")

    @staticmethod
    def _rows_from_params(params):
        rows: dict[int, dict] = {}
        for name, value in params.items():
            col, _, idx = name.rpartition("_m")
            if not idx.isdigit():
                continue
            rows.setdefault(int(idx), {})[col] = value
        return [rows[i] for i in sorted(rows)]

    def _upsert(self, incoming):
        seen = set()
        for row in incoming:
            key = (row["event_id"], row["dedupe_key"])
            if key in seen:
                # PostgreSQL: "ON CONFLICT DO UPDATE command cannot affect row a
                # second time" — a producer handing one key twice is the bug.
                raise UniqueViolation(f"duplicate in one statement: {key}")
            seen.add(key)
            if row["event_id"] in self.fail_insert_for:
                raise UniqueViolation(f"injected failure for event {row['event_id']}")
            existing = next(
                (
                    r
                    for r in self.staged
                    if (r["event_id"], r["dedupe_key"]) == key
                ),
                None,
            )
            if existing:
                existing.update(row)
            else:
                self.staged.append(dict(row))

    async def commit(self):
        self.store.rows = [dict(r) for r in self.staged]
        self.store.locks -= self.held_locks
        self.held_locks.clear()

    async def rollback(self):
        self.staged = [dict(r) for r in self.store.rows]
        self.store.locks -= self.held_locks
        self.held_locks.clear()

    async def close(self):
        pass


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


def _event_row(event_id=1, box=None):
    return SimpleNamespace(
        id=event_id,
        home_team_name="Phillies",
        away_team_name="Mets",
        box_score_data=box if box is not None else {"scoring_plays": []},
    )


def _snap(mins, home_prob, h, a):
    return SimpleNamespace(
        source="mlb",
        captured_at=_T0 + timedelta(minutes=mins),
        home_win_probability=home_prob,
        game_state={"home_score": h, "away_score": a, "period": "5"},
    )


def _scoring_series():
    """Snapshots that yield exactly one confident synthesized moment."""
    return [_snap(0, 0.50, 0, 0), _snap(20, 0.66, 1, 0)]


def _run(monkeypatch, session):
    @asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(gm, "get_task_session", _fake_session)
    return asyncio.run(gm._compute_game_moments(limit=10))


# --- the C59 cases ----------------------------------------------------------


class TestAuthoritativeReplacement:
    def test_clean_first_write(self, monkeypatch):
        store = Store()
        session = FakeSession(store, [_event_row(1)], {1: _scoring_series()})
        stats = _run(monkeypatch, session)
        assert stats["events_written"] == 1 and stats["events_failed"] == 0
        assert len(store.keys(1)) == 1

    def test_identical_rerun_updates_instead_of_inserting(self, monkeypatch):
        store = Store()
        events, snaps = [_event_row(1)], {1: _scoring_series()}
        _run(monkeypatch, FakeSession(store, events, snaps))
        first = store.keys(1)
        _run(monkeypatch, FakeSession(store, events, snaps))
        assert store.keys(1) == first  # no second row, no UniqueViolation

    def test_stale_keys_are_removed(self, monkeypatch):
        store = Store([{"event_id": 1, "dedupe_key": "m2:mlb:stale", "description": "old"}])
        _run(monkeypatch, FakeSession(store, [_event_row(1)], {1: _scoring_series()}))
        assert "m2:mlb:stale" not in store.keys(1)
        assert len(store.keys(1)) == 1

    def test_computed_empty_removes_stale_rows(self, monkeypatch):
        # Evidence exists (plays + snapshots) but nothing clears the join → the
        # empty result is authoritative; annotations must not outlive it.
        store = Store([{"event_id": 1, "dedupe_key": "m2:mlb:old", "description": "old"}])
        flat = [_snap(0, 0.50, 0, 0), _snap(20, 0.505, 1, 0)]  # +0.5pt: below MIN_DELTA
        monkeypatch.setattr(gm, "compute_moments", lambda *a, **k: [])
        stats = _run(monkeypatch, FakeSession(store, [_event_row(1)], {1: flat}))
        assert stats["events_empty"] == 1
        assert store.keys(1) == []

    def test_replacement_upserts_before_it_deletes(self, monkeypatch):
        # The v1 shape was DELETE-everything-then-INSERT, which (a) empties the
        # event mid-transaction and (b) races a concurrent run into the unique
        # constraint. The repair upserts first, then deletes only what the
        # canonical set no longer contains.
        store = Store([{"event_id": 1, "dedupe_key": "m2:mlb:old", "description": "old"}])
        session = FakeSession(store, [_event_row(1)], {1: _scoring_series()})
        _run(monkeypatch, session)
        writes = [
            s
            for s in session.statements
            if s.startswith(("INSERT INTO game_moments", "DELETE FROM game_moments"))
        ]
        assert len(writes) == 2
        assert writes[0].startswith("INSERT INTO game_moments")
        assert writes[1].startswith("DELETE FROM game_moments")
        assert "NOT IN" in writes[1]  # scoped to stale keys, never delete-all


class TestEvidencePreservation:
    def test_fetch_failure_preserves_prior_rows(self, monkeypatch):
        keep = [{"event_id": 1, "dedupe_key": "m2:mlb:keep", "description": "keep"}]
        store = Store(list(keep))
        session = FakeSession(store, [_event_row(1)], {1: RuntimeError("db down")})
        with pytest.raises(gm.GameMomentsRunFailure) as err:
            _run(monkeypatch, session)
        assert err.value.stats["events_failed"] == 1
        assert store.keys(1) == ["m2:mlb:keep"]  # truth survived the failure

    def test_insufficient_evidence_preserves_prior_rows(self, monkeypatch):
        store = Store([{"event_id": 1, "dedupe_key": "m2:mlb:keep", "description": "keep"}])
        stats = _run(
            monkeypatch, FakeSession(store, [_event_row(1)], {1: [_snap(0, 0.5, 0, 0)]})
        )
        assert stats["events_skipped"] == 1 and stats["events_failed"] == 0
        assert store.keys(1) == ["m2:mlb:keep"]

    def test_cancellation_preserves_rows_and_propagates(self, monkeypatch):
        store = Store([{"event_id": 1, "dedupe_key": "m2:mlb:keep", "description": "keep"}])
        session = FakeSession(store, [_event_row(1)], {1: asyncio.CancelledError()})
        with pytest.raises(asyncio.CancelledError):
            _run(monkeypatch, session)
        assert store.keys(1) == ["m2:mlb:keep"]


class TestIsolationAndOverlap:
    def test_poison_event_does_not_starve_healthy_sibling(self, monkeypatch):
        # #1445's actual damage: the first constraint failure aborted every later
        # event. The sibling must still commit — and the run must still be RED.
        store = Store()
        session = FakeSession(
            store,
            [_event_row(1), _event_row(2)],
            {1: _scoring_series(), 2: _scoring_series()},
        )
        session.fail_insert_for = {1}
        with pytest.raises(gm.GameMomentsRunFailure) as err:
            _run(monkeypatch, session)
        stats = err.value.stats
        assert stats["events_scanned"] == 2
        assert stats["events_failed"] == 1 and stats["events_written"] == 1
        assert stats["failures"][0]["event_id"] == 1
        assert store.keys(1) == [] and len(store.keys(2)) == 1

    def test_failure_is_never_reported_green(self, monkeypatch):
        store = Store()
        session = FakeSession(store, [_event_row(1)], {1: _scoring_series()})
        session.fail_insert_for = {1}
        with pytest.raises(gm.GameMomentsRunFailure):
            _run(monkeypatch, session)

    def test_replacement_takes_the_event_lock_before_any_write(self, monkeypatch):
        store = Store()
        session = FakeSession(store, [_event_row(7)], {7: _scoring_series()})
        _run(monkeypatch, session)
        mutations = [
            i
            for i, s in enumerate(session.statements)
            if s.startswith(("INSERT INTO game_moments", "DELETE FROM game_moments"))
        ]
        lock_at = next(
            i for i, s in enumerate(session.statements) if "pg_advisory_xact_lock" in s
        )
        assert mutations and lock_at < min(mutations)
        assert session.lock_keys == [(gm._LOCK_NAMESPACE, 7)]  # locked per event
        assert not store.locks  # transaction-scoped: released at COMMIT

    def test_overlapping_run_cannot_mutate_while_the_lock_is_held(self, monkeypatch):
        store = Store()
        holder = FakeSession(store, [], {})
        asyncio.run(
            holder.execute(
                gm.select(gm.func.pg_advisory_xact_lock(gm._LOCK_NAMESPACE, 1))
            )
        )
        session = FakeSession(store, [_event_row(1)], {1: _scoring_series()})
        with pytest.raises(gm.GameMomentsRunFailure) as err:
            _run(monkeypatch, session)
        assert isinstance(err.value.stats["failures"][0]["error"], str)
        assert store.rows == []  # blocked before it could touch a single row
        assert not any(
            s.startswith(("INSERT INTO", "DELETE FROM")) for s in session.statements
        )


class TestRollbackSafety:
    def test_event_selection_returns_scalars_not_orm_rows(self, monkeypatch):
        # Gotcha #6: a rollback expires ORM objects, so the loop must never hold
        # one across an event boundary.
        session = FakeSession(Store(), [_event_row(1)], {})
        rows = asyncio.run(gm._select_events(session, _T0, 10))
        assert rows == [{"id": 1, "home": "Phillies", "away": "Mets", "box": {"scoring_plays": []}}]
        assert all(isinstance(v, (int, str, dict)) for v in rows[0].values())

    def test_sibling_after_rollback_still_uses_preloaded_scalars(self, monkeypatch):
        store = Store()
        session = FakeSession(
            store,
            [_event_row(1), _event_row(2), _event_row(3)],
            {1: _scoring_series(), 2: RuntimeError("boom"), 3: _scoring_series()},
        )
        with pytest.raises(gm.GameMomentsRunFailure) as err:
            _run(monkeypatch, session)
        assert err.value.stats["events_written"] == 2
        assert len(store.keys(1)) == 1 and len(store.keys(3)) == 1


class TestTerminalStates:
    def test_every_selected_event_reaches_one_terminal_state(self, monkeypatch):
        store = Store()
        session = FakeSession(
            store,
            [_event_row(1), _event_row(2), _event_row(3)],
            {
                1: _scoring_series(),
                2: [_snap(0, 0.5, 0, 0)],  # insufficient evidence
                3: RuntimeError("boom"),
            },
        )
        with pytest.raises(gm.GameMomentsRunFailure) as err:
            _run(monkeypatch, session)
        stats = err.value.stats
        terminal = (
            stats["events_written"]
            + stats["events_empty"]
            + stats["events_skipped"]
            + stats["events_failed"]
            + stats["events_cancelled"]
        )
        assert terminal == stats["events_scanned"] == 3
