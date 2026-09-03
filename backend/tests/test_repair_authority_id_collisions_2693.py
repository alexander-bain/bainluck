"""#2693 step 2 — the write half: the rail, its two-call contract, its refusals.

The decider is tested next door (`test_authority_id_collisions_2693.py`). What
is pinned here is everything that could still go wrong once a correct decision
has been made:

  * an apply that re-derives instead of consuming the plan a human read;
  * an apply that writes a row whose id moved after the review;
  * a rail nobody can invoke, which is a plan object with extra steps;
  * a dark authority read as an absence — the failure mode gotcha #53 names,
    and the reason `AUTHORITY_UNAVAILABLE` writes nothing.
"""

from __future__ import annotations

import asyncio

import pytest

from app.tasks import repair_authority_id_collisions as rail


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Answers each statement from a scripted queue, and records the writes."""

    def __init__(self, script):
        self._script = list(script)
        self.executed = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return _Result(self._script.pop(0) if self._script else [])

    async def commit(self):
        self.commits += 1


CENSUS_BEFORE = [(196, 430)]
CENSUS_AFTER = [(8, 17)]


# ---------------------------------------------------------------------------
# The apply is bound to a plan a human read.
# ---------------------------------------------------------------------------


class TestApplyIsBoundToTheReviewedPlan:
    def test_an_apply_with_no_hash_is_refused_and_writes_nothing(self):
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=True))
        assert out["refused"] is True
        assert out["reason_codes"] == [rail.REASON_PLAN_REQUIRED]
        assert session.executed == []

    def test_a_hash_that_names_no_artifact_is_refused(self, monkeypatch):
        async def _none():
            return None, rail.REASON_PLAN_MISSING

        monkeypatch.setattr(rail, "_read_plan", _none)
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="deadbeef"))
        assert out["refused"] is True
        assert out["reason_codes"] == [rail.REASON_PLAN_MISSING]
        assert session.executed == []

    def test_a_stale_hash_is_refused_by_NAME_not_silently_re_derived(self, monkeypatch):
        """#1949: a work list that can be recomputed at apply time can differ
        from the one that was reviewed, and no after-measurement can say which
        of the two was written."""
        async def _plan():
            return {"plan_hash": "aaaa", "rows": [
                {"event_id": 1, "contested_espn_id": "9", "verdict": "AGREES_TWIN"}
            ]}, "ok"

        monkeypatch.setattr(rail, "_read_plan", _plan)
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="bbbb"))
        assert out["reason_codes"] == [rail.REASON_PLAN_MISMATCH]
        assert out["presented"] == "bbbb"
        assert out["stored"] == "aaaa"
        assert session.executed == []

    def test_unreadable_is_its_own_reason_and_not_folded_into_missing(self):
        """An operator told the plan is MISSING goes and makes one, which is
        the wrong move when it is there and the read fell over."""
        assert rail.REASON_PLAN_UNREADABLE != rail.REASON_PLAN_MISSING
        assert rail.REASON_PLAN_CORRUPT != rail.REASON_PLAN_MISSING


# ---------------------------------------------------------------------------
# The write: one column, the compare inside it, and a moved row named.
# ---------------------------------------------------------------------------


class TestTheWrite:
    @pytest.fixture(autouse=True)
    def _undo_record_persists(self, monkeypatch):
        """Let the apply past its backup precondition (D51, lane1/084).

        Since the undo record shipped, an apply writes NOTHING until this
        apply's own dated record is durably stored — so without this stub every
        assertion below would pass for the wrong reason (a sandbox with no
        Postgres refuses the apply, and "no write happened" is exactly what
        several of these tests check). Stubbing it keeps each test measuring
        what it was written to measure. The refusal itself, its ordering and
        the `superseded`-is-not-success rule are covered on their own in
        `test_authority_id_collisions_undo_d51.py`.
        """
        async def _saved(identity, payload):
            return True, "ok"

        async def _saved_co_commit(session, identity, payload):
            # Each row's receipt is co-committed with its unstamp since
            # CERT-851, so this is the seam the loop actually reaches. It must
            # still COMMIT: `test_it_commits_per_row_because_events_is_hot`
            # counts commits, and a stub that skipped it would measure the stub.
            await session.commit()
            return True, "ok"

        monkeypatch.setattr(rail, "_save_undo", _saved)
        monkeypatch.setattr(rail, "_save_undo_co_commit", _saved_co_commit)

    def _plan(self, monkeypatch, rows, digest="hash1"):
        async def _plan_reader():
            return {"plan_hash": digest, "rows": rows}, "ok"

        monkeypatch.setattr(rail, "_read_plan", _plan_reader)

    def test_it_unstamps_the_planned_rows_and_reports_the_census_both_sides(
        self, monkeypatch
    ):
        rows = [
            {"event_id": 15200817, "contested_espn_id": "401816574", "verdict": "TIME_DISAGREES"},
            {"event_id": 15201232, "contested_espn_id": "401816672", "verdict": "AGREES_TWIN"},
        ]
        self._plan(monkeypatch, rows)
        session = _FakeSession([
            CENSUS_BEFORE, [(15200817,)], [(15201232,)], CENSUS_AFTER,
        ])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="hash1"))
        assert out["unstamped"] == 2
        assert out["moved"] == []
        assert out["before"] == {"contested_ids": 196, "rows_wearing": 430}
        assert out["after"] == {"contested_ids": 8, "rows_wearing": 17}
        assert out["unstamped_by_verdict"] == {"AGREES_TWIN": 1, "TIME_DISAGREES": 1}

    def test_the_compare_is_in_the_write_and_carries_the_reviewed_id(
        self, monkeypatch
    ):
        """`AND espn_id = :contested` is what closes the hours-wide window
        between the review and the run. A check performed BEFORE the statement
        is a read of a world the write then changes."""
        self._plan(monkeypatch, [
            {"event_id": 42, "contested_espn_id": "999", "verdict": "AGREES_TWIN"}
        ])
        session = _FakeSession([CENSUS_BEFORE, [(42,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="hash1"))

        sql, params = session.executed[1]
        assert "espn_id = NULL" in sql.replace("SET espn_id=NULL", "SET espn_id = NULL")
        assert "AND espn_id = :contested" in sql
        assert params == {"event_id": 42, "contested": "999"}

    def test_it_writes_ONE_column_and_touches_no_other_table(self, monkeypatch):
        """Ruling 079's strong form here: no DELETE, no FK re-pointed, and not
        `status`, the scores or `completed_at` — those oscillate and #1981's
        writer owns them."""
        self._plan(monkeypatch, [
            {"event_id": 42, "contested_espn_id": "999", "verdict": "AGREES_TWIN"}
        ])
        session = _FakeSession([CENSUS_BEFORE, [(42,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="hash1"))

        writes = [
            sql for sql, _ in session.executed
            if "UPDATE" in sql.upper() or "DELETE" in sql.upper()
        ]
        assert len(writes) == 1
        write = writes[0].upper()
        assert "DELETE" not in write
        for forbidden in ("STATUS", "HOME_SCORE", "AWAY_SCORE", "COMPLETED_AT", "COMMENCE_TIME"):
            assert forbidden not in write

    def test_a_row_whose_id_moved_is_NAMED_never_a_silent_success(
        self, monkeypatch
    ):
        self._plan(monkeypatch, [
            {"event_id": 1, "contested_espn_id": "9", "verdict": "AGREES_TWIN"},
            {"event_id": 2, "contested_espn_id": "9", "verdict": "TEAMS_DISAGREE"},
        ])
        # Row 1 no longer holds `9` — RETURNING gives nothing.
        session = _FakeSession([CENSUS_BEFORE, [], [(2,)], CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="hash1"))

        assert out["unstamped"] == 1
        assert out["moved"] == [
            {"event_id": 1, "expected_espn_id": "9", "reason_code": "ESPN_ID_MOVED"}
        ]
        # A moved row must not cancel its approved siblings.
        assert out["rows_in_plan"] == 2

    def test_it_commits_per_row_because_events_is_hot(self, monkeypatch):
        self._plan(monkeypatch, [
            {"event_id": 1, "contested_espn_id": "9", "verdict": "AGREES_TWIN"},
            {"event_id": 2, "contested_espn_id": "8", "verdict": "AGREES_TWIN"},
        ])
        session = _FakeSession([CENSUS_BEFORE, [(1,)], [(2,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="hash1"))
        assert session.commits == 2

    def test_an_empty_plan_applies_cleanly_and_says_so(self, monkeypatch):
        self._plan(monkeypatch, [])
        session = _FakeSession([CENSUS_BEFORE, CENSUS_BEFORE])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="hash1"))
        assert out["unstamped"] == 0
        assert out["before"] == out["after"]


# ---------------------------------------------------------------------------
# The derive, and the authority reading that governs it.
# ---------------------------------------------------------------------------


class TestDerive:
    def test_a_dark_authority_plans_no_write_for_that_group(self, monkeypatch):
        """ESPN returns 502 for 401504210 today. An absent answer is not an
        answer (gotcha #53) — the group must survive the run, visible."""
        async def _no_record(service, sport_keys, authority_id):
            return None

        saved = {}

        async def _save(payload):
            saved.update(payload)
            return True, "ok"

        monkeypatch.setattr(rail, "_fetch_record", _no_record)
        monkeypatch.setattr(rail, "_save_plan", _save)

        session = _FakeSession([
            CENSUS_BEFORE,
            [("401504210", 14794949, "americanfootball_cfl", "Winnipeg Blue Bombers",
              "Toronto Argonauts", None, None, None, None, 0),
             ("401504210", 14970487, "americanfootball_cfl", "Winnipeg Blue Bombers",
              "Toronto Argonauts", None, None, None, None, 0)],
        ])
        out = asyncio.run(rail.repair(session))
        assert out["rows_planned"] == 0
        assert out["summary"]["outcomes"]["AUTHORITY_UNAVAILABLE"] == 1
        assert out["summary"]["groups_unresolved"] == 1
        assert [g["authority_id"] for g in out["residual"]] == ["401504210"]
        assert saved["rows"] == []

    def test_a_derive_never_writes(self, monkeypatch):
        async def _no_record(service, sport_keys, authority_id):
            return None

        async def _save(payload):
            return True, "ok"

        monkeypatch.setattr(rail, "_fetch_record", _no_record)
        monkeypatch.setattr(rail, "_save_plan", _save)
        session = _FakeSession([CENSUS_BEFORE, []])
        asyncio.run(rail.repair(session))
        assert session.commits == 0
        assert not any(
            "UPDATE" in sql.upper() or "DELETE" in sql.upper()
            for sql, _ in session.executed
        )

    def test_a_plan_that_could_not_be_persisted_hands_back_NO_hash(self, monkeypatch):
        """An operator who cannot be handed a hash must be told, because the
        next thing they will do is try to apply."""
        async def _no_record(service, sport_keys, authority_id):
            return None

        async def _fail(payload):
            return False, "persist rejected: rejected"

        monkeypatch.setattr(rail, "_fetch_record", _no_record)
        monkeypatch.setattr(rail, "_save_plan", _fail)
        session = _FakeSession([CENSUS_BEFORE, []])
        out = asyncio.run(rail.repair(session))
        assert out["plan_hash"] is None
        assert out["plan_persisted"] is False
        assert "rejected" in out["plan_note"]

    def test_the_derive_plans_the_unstamp_and_names_the_keeper(self, monkeypatch):
        from app.utils.authority_id_collisions import AuthorityRecord

        async def _record(service, sport_keys, authority_id):
            return AuthorityRecord(
                authority_id=authority_id,
                home_names=frozenset({"alabama crimson tide"}),
                away_names=frozenset({"ole miss rebels"}),
                label="Alabama Crimson Tide v Ole Miss Rebels",
            )

        async def _save(payload):
            return True, "ok"

        monkeypatch.setattr(rail, "_fetch_record", _record)
        monkeypatch.setattr(rail, "_save_plan", _save)
        session = _FakeSession([
            CENSUS_BEFORE,
            [("401847094", 14683176, "baseball_ncaa", "Alabama Crimson Tide",
              "Ole Miss Rebels", None, "hash", "148", "92", 12),
             ("401847094", 14707075, "baseball_ncaa", "North Alabama",
              "Ole Miss", None, None, "148", "92", 0)],
        ])
        out = asyncio.run(rail.repair(session))
        assert out["rows_planned"] == 1
        assert out["groups"][0]["keep_event_id"] == 14683176
        assert out["summary"]["groups_unresolved"] == 0

    def test_limit_bounds_the_derive_and_says_it_was_bounded(self, monkeypatch):
        async def _no_record(service, sport_keys, authority_id):
            return None

        async def _save(payload):
            return True, "ok"

        monkeypatch.setattr(rail, "_fetch_record", _no_record)
        monkeypatch.setattr(rail, "_save_plan", _save)
        session = _FakeSession([
            CENSUS_BEFORE,
            [("1", 10, "baseball_mlb", "A", "B", None, None, None, None, 0),
             ("2", 20, "baseball_mlb", "C", "D", None, None, None, None, 0)],
        ])
        out = asyncio.run(rail.repair(session, limit=1))
        assert out["groups_examined"] == 1
        assert out["groups_truncated"] is True


# ---------------------------------------------------------------------------
# The rail has an address somebody can call.
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_it_is_registered_in_the_repair_dispatcher(self):
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["authority-id-collisions"] == (
            "app.tasks.repair_authority_id_collisions", "repair"
        )

    def test_the_docstring_catalog_did_not_drift_from_the_registry_again(self):
        from app.routes import admin_repairs

        assert "authority-id-collisions" in (admin_repairs.__doc__ or ""), (
            "the docstring catalog has drifted from the registry again"
        )

    def test_the_dispatcher_passes_through_every_param_the_rail_declares(self):
        import inspect
        import re

        from app.routes import admin_repairs

        declared = set(inspect.signature(rail.repair).parameters) - {
            "session", "apply", "now",
        }
        src = inspect.getsource(admin_repairs.run_repair)
        passed = set(re.findall(r'\("(\w+)",\s*\w+\)', src))
        missing = sorted(declared - passed)
        assert not missing, f"declared but never passed through: {missing}"

    def test_it_is_NOT_on_the_beat_schedule(self):
        """Attended only. An id-handback that runs itself is an id-handback
        nobody reviewed."""
        from app.tasks import celery_app

        for name, entry in celery_app.conf.beat_schedule.items():
            assert "authority_id_collisions" not in str(entry.get("task", "")), name


class TestRecordFromSummaryIsSharedWithTheAudit:
    def test_the_rail_and_the_audit_script_read_ONE_decider(self):
        """The dry-run counts quoted in a PR and the counts the rail acts on
        must be the same numbers, or the review was of a different plan."""
        import app.utils.authority_id_collisions as decider

        assert rail.decide_group is decider.decide_group
        assert rail.summarize is decider.summarize
