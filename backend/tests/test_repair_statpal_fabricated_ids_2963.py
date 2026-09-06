"""#2963 — the 48 invented ``statpal_fixture_id`` values come out, reversibly.

``CERT-2081`` closed the producer: no StatPal row is created from an id we made
up. The 48 rows it already wrote are still there, each holding a
``statpal_live_<home>_<away>`` string, and each of them is a game whose REAL
StatPal id we already know — ``stamp_nfl_statpal_fixtures`` classifies the row
``POLLUTED`` and refuses to stamp it, because its write is guarded
``AND statpal_fixture_id IS NULL``. This rail clears the column so that stamp can
land.

What is pinned here is the set of properties that make it safe to run unattended
under D51, not the prose that claims them:

  * **membership is the classifier's, not a second copy of it** — flip
    ``is_statpal_contest_id`` and membership follows, which is only true while
    there is one rule;
  * **the gate is a content address, not a count** — changing a row's VALUE
    changes the plan hash, because a cardinality gate cannot tell 48 rows from
    48 different rows;
  * **nothing is written until this apply's own dated record is on disk**, and a
    record that cannot be written REFUSES the apply rather than being stepped
    over;
  * **the undo carries per-row prior values and the restore writes them per
    row** — the whole reason this is a sibling of ``statpal-blank-ids`` and not
    a parameter on it, since that rail restores one constant;
  * **a row that would lose its last anchor is refused, at WRITE time** — all 48
    carry an ``espn_id`` today, but a measurement is a reading of the past and
    ``prune_unanchored_duplicates`` deletes rows whose three anchor columns are
    all NULL;
  * **the SQL names columns that exist**, proved by running the real statements
    against a real engine rather than a fake session that would accept anything.

Every guard carries BOTH arms. "Nothing was written" alone passes for a rail
that never writes at all.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `Base.metadata.create_all` can build the real `events` table on
# sqlite. The column TYPES are irrelevant to what section 7 proves — it is
# checking that the statements name columns that exist and that the anchor
# clause selects what it claims — but without these the metadata will not
# render at all.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport  # noqa: E402
from app.tasks import repair_statpal_fabricated_ids as rail  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# Fakes
# ════════════════════════════════════════════════════════════════════════════


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Row:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeSession:
    """Answers each statement from a scripted queue, and records the writes.

    The census is answered out of band rather than out of the queue. It is read
    twice per run at fixed points, so making the script carry it couples every
    test to how many rows the run reached — and a test that stops the run early
    would then be answering an after-census with a leftover UPDATE result and
    failing for a reason that has nothing to do with what it asserts.
    """

    def __init__(self, script):
        self._script = list(script)
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, params))
        if "FILTER (WHERE statpal_fixture_id IS NULL)" in sql:
            return _Result(CENSUS_ROW)
        return _Result(self._script.pop(0) if self._script else [])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


CENSUS_ROW = [_Row(linked=3277, blank=0, nulls=229034, total=232311)]

PLAN_ROWS = [
    {
        "event_id": 15196983,
        "fabricated_id": "statpal_live_Las Vegas Raiders_Arizona Cardinals",
        "sport": "americanfootball_nfl",
        "matchup": "Las Vegas Raiders v Arizona Cardinals",
        "commence_time": "2026-08-16T00:00:00+00:00",
        "status": "completed",
        "espn_id": "401772936",
        "external_id": None,
    },
    {
        "event_id": 15292757,
        "fabricated_id": "statpal_live_Chicago Bears_Kansas City Chiefs",
        "sport": "americanfootball_nfl",
        "matchup": "Chicago Bears v Kansas City Chiefs",
        "commence_time": "2026-08-22T23:00:00+00:00",
        "status": "completed",
        "espn_id": "401772961",
        "external_id": None,
    },
]

#: Every payload the rail hands its writers carries the owner token, so a guard
#: calling one directly has to as well — a payload without it is refused before
#: the store is reached, which would make the test pass for the wrong reason.
OWNED = {"rows": [], rail.UNDO_OWNER_KEY: "inv0"}


def _plan_reader(rows=None, plan_hash="abc123def456"):
    async def _read():
        return {
            "plan_hash": plan_hash,
            "rows": list(PLAN_ROWS if rows is None else rows),
        }, "ok"

    return _read


def _wire_saves(monkeypatch, save):
    """Patch BOTH persistence seams from one fake, and make them behave.

    Each row's receipt is staged inside the SAME transaction as its clear, so
    the apply only reaches the standalone writer for the pre-write record and
    the final seal. Patching one seam and not the other leaves the real
    co-commit talking to a fake session. The adapter mirrors the real helper,
    rollback included: that rollback is what takes the clear back out.
    """
    monkeypatch.setattr(rail, "_save_undo", save)

    async def _co_commit(session, identity, payload):
        ok, note = await save(identity, payload)
        if ok:
            await session.commit()
        else:
            await session.rollback()
        return ok, note

    monkeypatch.setattr(rail, "_save_undo_co_commit", _co_commit)


def _clears(session):
    """Only the statements that clear the column — a census SELECT is not one."""
    return [
        (sql, params)
        for sql, params in session.executed
        if "SET statpal_fixture_id = NULL" in sql
    ]


def _restores(session):
    return [
        (sql, params)
        for sql, params in session.executed
        if "SET statpal_fixture_id = :prior" in sql
    ]


# ════════════════════════════════════════════════════════════════════════════
# 1. Membership is the classifier's rule, not a second copy of it
# ════════════════════════════════════════════════════════════════════════════


class TestMembership:
    @pytest.mark.parametrize(
        "value",
        [
            "statpal_live_Las Vegas Raiders_Arizona Cardinals",
            "statpal_live_Chicago Bears_Kansas City Chiefs",
        ],
    )
    def test_an_invented_string_is_fabricated(self, value):
        assert rail.is_fabricated(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "280500",       # NFL contestid, 6 digits
            "1329190539",   # MLB, 10 digits
            "637968",       # the shape the blanks rail's duplicates carry
        ],
    )
    def test_a_real_statpal_id_is_not(self, value):
        assert rail.is_fabricated(value) is False

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_absence_is_not_fabricated(self, value):
        """Blank and NULL are ABSENCE, and `statpal-blank-ids` owns the blank half.

        Folding them in here would make this rail write NULL over NULL and, worse,
        put ``''`` into an undo record as though it were a value worth restoring.
        """
        assert rail.is_fabricated(value) is False

    def test_membership_follows_the_classifier_rather_than_restating_it(
        self, monkeypatch
    ):
        """THE POINT OF THE IMPORT, and the only test that can see it.

        Every assertion above passes just as well for a rail that hardcodes a
        ``statpal_live_`` prefix check — which would be a second copy of a rule
        that already exists in ``stamp_nfl_statpal_fixtures``, free to drift from
        it. Flip the classifier's answer and membership must flip with it: that
        can only hold while there is exactly one rule.
        """
        real = "statpal_live_Las Vegas Raiders_Arizona Cardinals"
        assert rail.is_fabricated(real) is True

        # Now the classifier says this IS an id (as it would if the id space
        # ever admitted such a string). Membership must follow.
        monkeypatch.setattr(rail, "is_statpal_contest_id", lambda v: True)
        assert rail.is_fabricated(real) is False

        # And the other direction: a value the classifier stops recognising.
        monkeypatch.setattr(rail, "is_statpal_contest_id", lambda v: False)
        assert rail.is_fabricated("280500") is True

    def test_the_plan_keeps_only_fabricated_rows(self):
        rows = rail.plan_rows_from_candidates([
            _Row(
                id=1, statpal_fixture_id="280500", sport="americanfootball_nfl",
                home_team_name="A", away_team_name="B", commence_time=None,
                status="completed", espn_id="401", external_id=None,
            ),
            _Row(
                id=2, statpal_fixture_id="statpal_live_A_B",
                sport="americanfootball_nfl", home_team_name="A",
                away_team_name="B", commence_time=None, status="completed",
                espn_id="402", external_id=None,
            ),
            _Row(
                id=3, statpal_fixture_id=None, sport="americanfootball_nfl",
                home_team_name="C", away_team_name="D", commence_time=None,
                status="scheduled", espn_id="403", external_id=None,
            ),
        ])
        assert [r["event_id"] for r in rows] == [2]
        assert rows[0]["fabricated_id"] == "statpal_live_A_B"


# ════════════════════════════════════════════════════════════════════════════
# 2. The gate is a content address, not a count
# ════════════════════════════════════════════════════════════════════════════


class TestPlanHash:
    def test_the_same_work_hashes_the_same(self):
        """A reviewer who re-runs the dry run to look again must not be refused."""
        assert rail.plan_hash_for(PLAN_ROWS) == rail.plan_hash_for(list(PLAN_ROWS))

    def test_a_changed_value_on_the_same_id_changes_the_hash(self):
        """THE REASON THIS IS NOT A COUNT GATE.

        ``statpal-blank-ids`` gates on an exact population COUNT, which is right
        when every row in the population is interchangeable — all 8,272 held
        ``''``. Here the rows are not interchangeable: same id, different string
        is different work, and a cardinality gate would wave it through.
        """
        moved = [dict(PLAN_ROWS[0], fabricated_id="statpal_live_Raiders_Cardinals"),
                 PLAN_ROWS[1]]
        assert len(moved) == len(PLAN_ROWS)          # a count gate sees no change
        assert rail.plan_hash_for(moved) != rail.plan_hash_for(PLAN_ROWS)

    def test_a_different_row_changes_the_hash(self):
        swapped = [dict(PLAN_ROWS[0], event_id=999), PLAN_ROWS[1]]
        assert rail.plan_hash_for(swapped) != rail.plan_hash_for(PLAN_ROWS)

    def test_labels_do_not_change_the_hash(self):
        """Over the WORK, not over the report.

        The matchup string and the status are read from the row at derive time
        and can legitimately change (a game finishes) without changing what this
        repair would write. Hashing them would refuse a plan the operator read.
        """
        relabelled = [
            dict(r, matchup="something else", status="closed", commence_time=None)
            for r in PLAN_ROWS
        ]
        assert rail.plan_hash_for(relabelled) == rail.plan_hash_for(PLAN_ROWS)


# ════════════════════════════════════════════════════════════════════════════
# 3. An apply is bound to a reviewed plan
# ════════════════════════════════════════════════════════════════════════════


class TestApplyIsBoundToAPlan:
    def test_no_plan_hash_refuses_and_writes_nothing(self):
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=True))
        assert out["refused"] is True
        assert rail.REASON_PLAN_REQUIRED in out["reason_codes"]
        assert _clears(session) == []

    def test_a_stale_hash_refuses_and_writes_nothing(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_plan", _plan_reader(plan_hash="STORED"))
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="PRESENTED"))
        assert out["refused"] is True
        assert rail.REASON_PLAN_MISMATCH in out["reason_codes"]
        assert out["stored"] == "STORED" and out["presented"] == "PRESENTED"
        assert _clears(session) == []

    def test_a_matching_hash_does_write(self, monkeypatch):
        """The other arm. Without it every refusal guard above is satisfied by
        a rail that refuses everything."""
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())

        async def _save(identity, payload):
            return True, "ok"

        _wire_saves(monkeypatch, _save)
        session = _FakeSession([
            [_Row(id=15196983)],
            [_Row(id=15292757)],
            ])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))
        assert out.get("refused") is not True
        assert out["cleared"] == 2
        assert len(_clears(session)) == 2


# ════════════════════════════════════════════════════════════════════════════
# 4. D51 — nothing is written before the backup exists
# ════════════════════════════════════════════════════════════════════════════


class TestTheBackupIsAPrecondition:
    def test_an_unwritable_record_refuses_the_whole_apply(self, monkeypatch):
        """These values exist NOWHERE ELSE once cleared.

        A cleared row is indistinguishable from the 229,034 that were always
        NULL, so a clear whose receipt failed is not "a clear with a missing
        note" — it is data destroyed. The apply must not start.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())

        async def _save(identity, payload):
            return False, "undo persist rejected: occupied"

        _wire_saves(monkeypatch, _save)
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))
        assert out["refused"] is True
        assert rail.REASON_UNDO_UNWRITTEN in out["reason_codes"]
        assert out["cleared"] == 0
        assert _clears(session) == []

    def test_the_first_record_claims_nothing(self, monkeypatch):
        """Written BEFORE the first clear, and therefore empty.

        A pre-write record that already named the planned rows would claim rows
        that may never be written — CERT-846's defect on the sibling rail, where
        the undo put a value back onto a row the apply never touched.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        seen: list[dict] = []

        async def _save(identity, payload):
            seen.append(payload)
            return True, "ok"

        _wire_saves(monkeypatch, _save)
        session = _FakeSession([
            [_Row(id=15196983)], [_Row(id=15292757)], ])
        asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))
        assert seen[0]["rows"] == []
        assert seen[0]["receipt_complete"] is False
        # ...and it already knows what it MEANT to do, for the operator.
        assert len(seen[0]["rows_planned"]) == 2

    def test_a_superseded_write_is_a_failure_for_a_receipt(self):
        """`_save_plan` counts ``superseded`` a success; a receipt must not.

        For a plan, a newer copy winning means the durability contract holds.
        For a receipt it means the record on file is somebody else's, so the
        restore command handed back would put back the wrong rows.
        """
        ok, note = rail._classify_undo_write("id", "superseded")
        assert ok is False and "SUPERSEDED" in note
        ok, note = rail._classify_undo_write("id", "occupied")
        assert ok is False and "OCCUPIED" in note
        assert rail._classify_undo_write("id", "ok") == (True, "ok")

    def test_a_record_with_no_owner_is_never_written(self):
        """The owner token is what stops a concurrent apply overwriting this
        receipt, so a payload without one is refused rather than stored."""
        ok, note = asyncio.run(rail._save_undo("id", {"rows": []}))
        assert ok is False and rail.UNDO_OWNER_KEY in note

    def test_an_unownable_payload_rolls_the_data_write_back(self):
        """And on the co-commit seam the refusal takes the UPDATE with it."""
        session = _FakeSession([])
        ok, note = asyncio.run(
            rail._save_undo_co_commit(session, "id", {"rows": []})
        )
        assert ok is False
        assert session.rollbacks == 1 and session.commits == 0


# ════════════════════════════════════════════════════════════════════════════
# 5. The compare is in the write, and every row reaches a named verdict
# ════════════════════════════════════════════════════════════════════════════


class TestPerRowVerdicts:
    def _run(self, monkeypatch, script):
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        saved: list[dict] = []

        async def _save(identity, payload):
            saved.append(payload)
            return True, "ok"

        _wire_saves(monkeypatch, _save)
        session = _FakeSession(script)
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))
        return out, session, saved

    def test_the_clear_carries_the_exact_reviewed_value(self, monkeypatch):
        out, session, _ = self._run(monkeypatch, [
            [_Row(id=15196983)], [_Row(id=15292757)], ])
        params = [p for _, p in _clears(session)]
        assert params[0]["fabricated"] == PLAN_ROWS[0]["fabricated_id"]
        assert params[1]["fabricated"] == PLAN_ROWS[1]["fabricated_id"]
        assert out["cleared"] == 2

    def test_a_moved_value_is_named_and_never_receipted(self, monkeypatch):
        """The stamper got there first, or a sibling apply did.

        The row's current value is NOT the one reviewed, so this apply did not
        write it — and an undo that put the reviewed value back would overwrite
        whatever did.
        """
        out, _, saved = self._run(monkeypatch, [
            [],                                     # first clear: no rowcount
            [_Row(statpal_fixture_id="280500", espn_id="401772936",
                  external_id=None)],               # why: the value moved
            [_Row(id=15292757)],                    # second clear lands
            ])
        assert out["cleared"] == 1
        assert [m["reason_code"] for m in out["moved"]] == ["STATPAL_ID_MOVED"]
        assert out["moved"][0]["event_id"] == 15196983
        assert out["moved"][0]["observed_statpal_fixture_id"] == "280500"
        receipted_ids = [r["event_id"] for r in saved[-1]["rows"]]
        assert 15196983 not in receipted_ids and 15292757 in receipted_ids

    def test_a_row_that_would_lose_its_last_anchor_is_refused_not_cleared(
        self, monkeypatch
    ):
        """``prune_unanchored_duplicates`` deletes rows with all three anchor
        columns NULL. Clearing the third one here would hand the row to it, so
        this repair would have caused a DELETION.

        Named separately from STATPAL_ID_MOVED on purpose: one says somebody
        else moved the value, the other says we declined to write.
        """
        out, _, saved = self._run(monkeypatch, [
            [],                                     # first clear: refused by SQL
            [_Row(statpal_fixture_id=PLAN_ROWS[0]["fabricated_id"],
                  espn_id=None, external_id=None)], # why: no other anchor
            [_Row(id=15292757)],
            ])
        assert [r["reason_code"] for r in out["refused"]] == ["WOULD_ORPHAN_ROW"]
        assert out["refused"][0]["event_id"] == 15196983
        assert out["cleared"] == 1
        assert 15196983 not in [r["event_id"] for r in saved[-1]["rows"]]
        assert "WOULD_ORPHAN_ROW" in out["note"]

    def test_a_receipt_failure_stops_the_apply(self, monkeypatch):
        """The helper's rollback took that row's UPDATE with it, so the run
        stops with nothing unclaimed rather than pressing on."""
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        calls = {"n": 0}

        async def _save(identity, payload):
            calls["n"] += 1
            # 1 = the pre-write record, 2 = the first row's co-commit.
            return (calls["n"] != 2), ("ok" if calls["n"] != 2 else "store down")

        _wire_saves(monkeypatch, _save)
        session = _FakeSession([
            [_Row(id=15196983)], [_Row(id=15292757)], ])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))
        assert out["cleared"] == 0
        assert out["receipt_complete"] is False
        assert rail.REASON_UNDO_RECEIPT_FAILED in out["reason_codes"]
        assert session.rollbacks == 1
        # It stopped: the second row was never attempted.
        assert len(_clears(session)) == 1

    def test_the_receipt_carries_a_prior_value_PER_ROW(self, monkeypatch):
        """THE REASON THIS IS A SIBLING AND NOT A PARAMETER.

        ``statpal-blank-ids`` states its prior value ONCE for 8,272 rows because
        they all held ``''``. Here every row holds a different string, so the
        record must carry one per row — and a restore driven off a single
        constant would write the same wrong string onto all of them.
        """
        _, _, saved = self._run(monkeypatch, [
            [_Row(id=15196983)], [_Row(id=15292757)], ])
        rows = saved[-1]["rows"]
        priors = [r["prior_statpal_fixture_id"] for r in rows]
        assert priors == [
            PLAN_ROWS[0]["fabricated_id"], PLAN_ROWS[1]["fabricated_id"]
        ]
        assert len(set(priors)) == 2, "each row must keep its OWN prior value"


# ════════════════════════════════════════════════════════════════════════════
# 6. The restore puts back exactly what the apply took
# ════════════════════════════════════════════════════════════════════════════


RECEIPT = {
    "plan_hash": "abc123def456",
    "taken_at": datetime(2026, 9, 6, 16, 0, tzinfo=timezone.utc).isoformat(),
    rail.UNDO_OWNER_KEY: "inv0",
    "rows": [
        {"event_id": 15196983,
         "prior_statpal_fixture_id": PLAN_ROWS[0]["fabricated_id"]},
        {"event_id": 15292757,
         "prior_statpal_fixture_id": PLAN_ROWS[1]["fabricated_id"]},
    ],
    "rows_planned": [
        {"event_id": 15196983,
         "prior_statpal_fixture_id": PLAN_ROWS[0]["fabricated_id"]},
        {"event_id": 15292757,
         "prior_statpal_fixture_id": PLAN_ROWS[1]["fabricated_id"]},
        {"event_id": 999, "prior_statpal_fixture_id": "statpal_live_X_Y"},
    ],
    "receipt_complete": True,
}


def _receipt_reader(payload=None, reason="ok"):
    async def _read(identity):
        return (RECEIPT if payload is None else payload), reason

    return _read


class TestTheRestore:
    def test_a_dry_run_writes_nothing(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_undo", _receipt_reader())
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=False, undo_identity="id"))
        assert out["rows_in_record"] == 2
        assert _restores(session) == []

    def test_each_row_gets_its_own_string_back(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_undo", _receipt_reader())
        session = _FakeSession([
            [_Row(id=15196983)], [_Row(id=15292757)], ])
        out = asyncio.run(rail.repair(session, apply=True, undo_identity="id"))
        assert out["restored"] == 2
        written = [p["prior"] for _, p in _restores(session)]
        assert written == [
            PLAN_ROWS[0]["fabricated_id"], PLAN_ROWS[1]["fabricated_id"]
        ]
        assert len(set(written)) == 2

    def test_it_replays_the_receipt_not_the_plan(self, monkeypatch):
        """CERT-846. The record plans three rows and receipts two; the row the
        apply never cleared must not have a value written onto it."""
        monkeypatch.setattr(rail, "_read_undo", _receipt_reader())
        session = _FakeSession([
            [_Row(id=15196983)], [_Row(id=15292757)], ])
        out = asyncio.run(rail.repair(session, apply=True, undo_identity="id"))
        assert out["rows_planned_in_record"] == 3 and out["rows_in_record"] == 2
        assert 999 not in [p["event_id"] for _, p in _restores(session)]
        assert "STATPAL_ID_MOVED" in out["note"]

    def test_a_row_that_now_holds_a_real_id_is_left_alone(self, monkeypatch):
        """AND THIS IS THE SUCCESS CASE, not a failure.

        Clearing the column is what lets ``stamp_nfl_statpal_fixtures`` write the
        real StatPal id. Writing the invented string back over it would make the
        undo cause the corruption it exists to reverse, so the ``IS NULL``
        compare refuses it — reported, never silently skipped.
        """
        monkeypatch.setattr(rail, "_read_undo", _receipt_reader())
        session = _FakeSession([
            [],                       # the IS NULL compare refused this row
            [_Row(id=15292757)],
            ])
        out = asyncio.run(rail.repair(session, apply=True, undo_identity="id"))
        assert out["restored"] == 1
        assert [r["reason_code"] for r in out["reoccupied"]] == [
            "STATPAL_ID_REOCCUPIED"
        ]
        assert out["reoccupied"][0]["event_id"] == 15196983

    def test_a_missing_record_refuses_rather_than_re_deriving(self, monkeypatch):
        monkeypatch.setattr(
            rail, "_read_undo", _receipt_reader(payload=None, reason=rail.REASON_UNDO_MISSING)
        )

        async def _read(identity):
            return None, rail.REASON_UNDO_MISSING

        monkeypatch.setattr(rail, "_read_undo", _read)
        session = _FakeSession([])
        out = asyncio.run(rail.repair(session, apply=True, undo_identity="id"))
        assert out["refused"] is True
        assert rail.REASON_UNDO_MISSING in out["reason_codes"]
        assert _restores(session) == []

    def test_an_undo_is_never_also_a_derive(self, monkeypatch):
        """``undo_identity`` takes precedence over every other argument, so an
        operator cannot accidentally re-plan while reversing."""
        monkeypatch.setattr(rail, "_read_undo", _receipt_reader())

        async def _boom():
            raise AssertionError("the derive must not run during an undo")

        monkeypatch.setattr(rail, "_read_plan", _boom)
        session = _FakeSession([])
        out = asyncio.run(
            rail.repair(session, apply=False, plan_hash="x", undo_identity="id")
        )
        assert out["undo"] is True


# ════════════════════════════════════════════════════════════════════════════
# 7. The SQL names columns that exist, proved against a real engine
# ════════════════════════════════════════════════════════════════════════════


class TestTheStatementsAreReal:
    """A fake session answers ANY statement, including one naming a column that
    does not exist. Every guard above would pass for SQL saying ``espn_event_id``
    — a name this codebase also uses, on other tables. So the statements are run
    against a real engine built from the real metadata.
    """

    @pytest.fixture
    def engine(self):
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng)
        with Session(eng) as s:
            s.add(Sport(id=1, key="americanfootball_nfl", name="NFL"))
            s.add(Event(
                id=15196983, sport_id=1, home_team_name="Las Vegas Raiders",
                away_team_name="Arizona Cardinals",
                commence_time=datetime(2026, 8, 16, tzinfo=timezone.utc),
                status="completed", espn_id="401772936",
                statpal_fixture_id=PLAN_ROWS[0]["fabricated_id"],
            ))
            # The row with NO other anchor: the write must refuse it.
            s.add(Event(
                id=15292757, sport_id=1, home_team_name="Chicago Bears",
                away_team_name="Kansas City Chiefs",
                commence_time=datetime(2026, 8, 22, tzinfo=timezone.utc),
                status="completed", espn_id=None, external_id=None,
                statpal_fixture_id=PLAN_ROWS[1]["fabricated_id"],
            ))
            s.commit()
        return eng

    def _value(self, eng, event_id):
        with Session(eng) as s:
            return s.execute(
                text("SELECT statpal_fixture_id FROM events WHERE id = :i"),
                {"i": event_id},
            ).scalar()

    def test_the_candidate_query_runs_and_finds_the_polluted_rows(self, engine):
        with Session(engine) as s:
            rows = s.execute(rail.CANDIDATE_SQL).all()
        planned = rail.plan_rows_from_candidates(rows)
        assert sorted(r["event_id"] for r in planned) == [15196983, 15292757]
        assert planned[0]["sport"] == "americanfootball_nfl"

    def test_the_census_query_runs(self, engine):
        with Session(engine) as s:
            row = s.execute(rail.CENSUS_SQL).first()
        assert row.linked == 2 and row.nulls == 0 and row.total == 2

    def test_the_clear_writes_the_anchored_row(self, engine):
        with Session(engine) as s:
            got = s.execute(rail.CLEAR_SQL, {
                "event_id": 15196983,
                "fabricated": PLAN_ROWS[0]["fabricated_id"],
            }).first()
            s.commit()
        assert got is not None
        assert self._value(engine, 15196983) is None

    def test_the_clear_refuses_the_row_with_no_other_anchor(self, engine):
        """The anchor clause is real SQL doing real work, not a comment."""
        with Session(engine) as s:
            got = s.execute(rail.CLEAR_SQL, {
                "event_id": 15292757,
                "fabricated": PLAN_ROWS[1]["fabricated_id"],
            }).first()
            s.commit()
        assert got is None
        assert self._value(engine, 15292757) == PLAN_ROWS[1]["fabricated_id"]

    def test_the_clear_refuses_a_value_that_moved(self, engine):
        with Session(engine) as s:
            got = s.execute(rail.CLEAR_SQL, {
                "event_id": 15196983, "fabricated": "something else",
            }).first()
            s.commit()
        assert got is None
        assert self._value(engine, 15196983) == PLAN_ROWS[0]["fabricated_id"]

    def test_the_miss_query_runs_and_explains_the_refusal(self, engine):
        with Session(engine) as s:
            row = s.execute(rail.CLEAR_MISS_SQL, {"event_id": 15292757}).first()
        assert row.espn_id is None and row.external_id is None
        assert row.statpal_fixture_id == PLAN_ROWS[1]["fabricated_id"]

    def test_the_restore_writes_only_over_null(self, engine):
        with Session(engine) as s:
            s.execute(rail.CLEAR_SQL, {
                "event_id": 15196983,
                "fabricated": PLAN_ROWS[0]["fabricated_id"],
            })
            s.commit()
            put_back = s.execute(rail.RESTORE_SQL, {
                "event_id": 15196983, "prior": PLAN_ROWS[0]["fabricated_id"],
            }).first()
            s.commit()
        assert put_back is not None
        assert self._value(engine, 15196983) == PLAN_ROWS[0]["fabricated_id"]

        # ...and now that the column is occupied again, a second restore is
        # refused rather than overwriting it. That is the STATPAL_ID_REOCCUPIED
        # arm, proved by the database rather than by a scripted fake.
        with Session(engine) as s:
            again = s.execute(rail.RESTORE_SQL, {
                "event_id": 15196983, "prior": "statpal_live_something_else",
            }).first()
            s.commit()
        assert again is None
        assert self._value(engine, 15196983) == PLAN_ROWS[0]["fabricated_id"]


# ════════════════════════════════════════════════════════════════════════════
# 8. Wiring — the rail is reachable and the restore command is real
# ════════════════════════════════════════════════════════════════════════════


class TestWiring:
    def test_the_repair_is_registered(self):
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["statpal-fabricated-ids"] == (
            "app.tasks.repair_statpal_fabricated_ids", "repair",
        )

    def test_the_dispatcher_can_forward_every_param_the_rail_needs(self):
        """The route passes an optional param through ONLY to a repair whose
        signature declares it. A gate the dispatcher cannot forward is a gate
        that silently never fires."""
        params = inspect.signature(rail.repair).parameters
        for name in ("apply", "plan_hash", "limit", "undo_identity"):
            assert name in params, f"{name} would never reach the rail"

    def test_the_restore_script_exists_and_agrees_on_the_identity_prefix(self):
        """--list greps the durable store by prefix. A rename on one side alone
        orphans every record the other side wrote."""
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts" / "restore_statpal_fabricated_ids.py"
        )
        assert script.exists()
        text_ = script.read_text()
        assert f'UNDO_IDENTITY_PREFIX = "{rail.UNDO_IDENTITY_PREFIX}"' in text_
        assert "/api/admin/repairs/statpal-fabricated-ids" in text_

    def test_the_undo_command_is_runnable_and_carries_this_run_s_identity(self):
        """D51 wants a one-command restore. An operator who has to work out how
        to reverse a write does not have a reversible write."""
        identity = rail.undo_identity_for(
            "abc123def456",
            at=datetime(2026, 9, 6, 16, 0, tzinfo=timezone.utc),
            invocation="inv0",
        )
        cmd = rail.restore_command(identity)
        assert cmd.startswith("python3 scripts/restore_statpal_fabricated_ids.py")
        assert identity in cmd and "--apply" in cmd

    def test_two_applies_starting_together_get_different_identities(self):
        """CERT-856. The clock and the plan hash are the two things concurrent
        applies agree on, so the token is what keeps one from overwriting the
        other's receipt."""
        at = datetime(2026, 9, 6, 16, 0, tzinfo=timezone.utc)
        a = rail.undo_identity_for("plan", at=at, invocation=rail.new_undo_invocation())
        b = rail.undo_identity_for("plan", at=at, invocation=rail.new_undo_invocation())
        assert a != b
