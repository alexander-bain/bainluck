"""CAL-P1008 (#1852 / #2528): the drain must be reversible from batch two onward.

The drain is capped at :data:`APPLY_MARKET_CAP` markets per call and the
population is 63,733 legs, so it runs many batches. The reviewed plan — the only
per-leg record of which leg got which verdict — lives in ONE durable slot, and
batch N+1's dry-run overwrites batch N's.

That is survivable for the retraction arm, which stamps ``ungradeable_result``
and can therefore be found again from the database alone. It is NOT survivable
for the restore arm, which sets ``is_winner = true`` and writes
``api_settlement`` back over ``api_settlement``: a restored leg is indisting-
uishable from a Kalshi winner nobody ever touched. Once the slot is overwritten
there is nothing, anywhere, that names the rows it flipped.

So the dry-run response carries ``plan_artifact`` — the byte-identical banked
payload — and the operator's captured response is the backup. These tests prove
the four things that claim rests on:

1. the artifact in the response RE-DECODES to the response's own ``plan_hash``,
   so it is restorable and not merely descriptive;
2. it is the same object that was banked, not a second derivation beside it;
3. batch two really does destroy batch one's slot, and the captured batch-one
   response really does survive it;
4. the restore arm really does leave no marker in the row — which is what makes
   (1)-(3) load-bearing rather than belt-and-braces.

Reverting the ``plan_artifact`` line turns 1, 2 and 3 red.
"""

from __future__ import annotations

import copy
import sys
from types import SimpleNamespace

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.tasks.calibration_main_build import CHECKPOINT_IDENTITY
from app.utils.calibration_invalidation import (
    REAPPLY_DISCHARGES,
    RESTORE_DISCHARGES,
    discharge_obligation,
    new_obligation,
    obligation_contains,
    obligation_market_ids,
    obligation_retry_instruction,
)
from app.utils.kalshi_fabricated_loss import (
    REPAIRABLE_SOURCE,
    RETRACTION_SOURCE,
    WRITING_VERDICTS,
    classify_leg,
)
from app.utils.repair_apply_plan import (
    APPLY_PLAN_SCHEMA,
    REASON_APPLIED_CORRUPT,
    REASON_APPLIED_MISSING,
    REASON_APPLIED_SOURCE_MISMATCH,
    PlannedLeg,
    applied_receipt_contains,
    build_applied_receipt,
    build_plan,
    decode_applied_receipt,
    decode_plan,
)
from app.utils.durable_state import EnvelopeRead
from tests.test_kalshi_fabricated_loss_p062 import (
    _CASSession,
    _FakeResult,
    _seeded_store,
)

# ---------------------------------------------------------------------------
# A two-market population, one batch each, each batch mixing BOTH write arms.
# Mixing them is the point: `plan_leg_ids` cannot separate the arms, so a batch
# with only one of them could not show what is missing.
# ---------------------------------------------------------------------------

_VENUE = {
    "KX-A": [
        {"ticker": "KX-A-T1", "status": "finalized", "result": "yes"},
        {"ticker": "KX-A-T2", "status": "finalized", "result": "scalar"},
        {"ticker": "KX-A-T3", "status": "finalized", "result": "no"},
    ],
    "KX-B": [
        {"ticker": "KX-B-T1", "status": "finalized", "result": "yes"},
        {"ticker": "KX-B-T2", "status": "finalized", "result": "scalar"},
    ],
}

_LEGS = {
    100: [(1, "KX-A-T1"), (2, "KX-A-T2"), (3, "KX-A-T3")],
    200: [(4, "KX-B-T1"), (5, "KX-B-T2")],
}

#: What each leg's verdict comes out as, given `_VENUE` — restated here so a
#: change in the classifier shows up as a failure in this file's premises
#: rather than silently reshaping what it is proving.
_EXPECTED_VERDICTS = {
    1: "restore_winner",
    2: "retract_fabricated",
    3: "confirmed_loss",
    4: "restore_winner",
    5: "retract_fabricated",
}


class _Rows:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def all(self):
        return self._rows


class _DryRunSession:
    """Enough of a session for the SELECT half. It never writes."""

    def __init__(self) -> None:
        self.work_rows = [
            SimpleNamespace(
                market_id=100,
                event_ticker="KX-A",
                age_days=10.0,
                mutex=True,
                resolution_date="2026-07-24",
            ),
            SimpleNamespace(
                market_id=200,
                event_ticker="KX-B",
                age_days=11.0,
                mutex=True,
                resolution_date="2026-07-25",
            ),
        ]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "statement_timeout" in sql:
            return _Rows([])
        params = params or {}
        if "mid" in params:
            return _Rows(
                [
                    SimpleNamespace(
                        id=leg_id,
                        external_id=ticker,
                        is_winner=False,
                        resolution_source=REPAIRABLE_SOURCE,
                    )
                    for leg_id, ticker in _LEGS[params["mid"]]
                ]
            )
        after_id = params.get("after_id")
        rows = [
            r for r in self.work_rows if after_id is None or r.market_id > int(after_id)
        ]
        return _Rows(rows[: int(params.get("lim") or len(rows))])

    async def rollback(self):  # pragma: no cover - only on a select failure
        pass


class _Venue:
    def __init__(self) -> None:
        self.closed = False

    async def get_markets(
        self, *, status=None, event_ticker=None, limit=None, cursor=None
    ):
        return _VENUE.get(event_ticker, []), None

    async def close(self):
        self.closed = True


#: The store the current test installed. `_UndoSession` needs it to apply its
#: staged durable writes on commit, and threading it through every construction
#: site would obscure what each test is actually saying.
_CURRENT_STORE = None


def _txn_store(monkeypatch):
    """The seeded one-slot store, with the in-transaction pair installed."""
    return _install_txn_durables(_seeded_store(monkeypatch), monkeypatch)


def _install_txn_durables(store, monkeypatch):
    """Teach the p062 store the IN-TRANSACTION pair, and model atomicity.

    CERT-1858's repair turns on the applied receipt landing in the same
    transaction as the rows, so a store whose writes take effect immediately
    could not tell the fixed rail from the broken one. Here a
    ``publish_snapshot_in_txn`` is held on the SESSION until that session
    commits, and discarded if it rolls back — which is the whole property under
    test.
    """
    import app.services.durable_snapshots as ds

    async def _read_in_txn(db, identity, *, expected_version=None, max_age_s=None):
        for env in getattr(db, "pending_durable", []):
            if env.identity == identity:
                return EnvelopeRead(status="ok", tier="durable", envelope=env)
        return await store.read(
            identity, expected_version=expected_version, max_age_s=max_age_s
        )

    async def _publish_in_txn(db, envelope):
        """Production semantics, including the one that bit CERT-1863.

        `superseded` means a NEWER generation already sits at the identity, so
        the real implementation writes NOTHING and answers `superseded`. A fake
        that staged anyway would make the containment gate untestable — which is
        exactly how the bug survived presentation four.
        """
        status = store.forced_status.get(envelope.identity, "ok")
        if status == "ok":
            db.pending_durable.append(envelope)
        return {
            "status": status,
            "identity": envelope.identity,
            "generation": envelope.generation,
        }

    monkeypatch.setattr(ds, "read_snapshot", _read_in_txn)
    monkeypatch.setattr(ds, "publish_snapshot_in_txn", _publish_in_txn)
    global _CURRENT_STORE
    _CURRENT_STORE = store
    monkeypatch.setattr(sys.modules[__name__], "_CURRENT_STORE", store, raising=False)
    return store


@pytest.fixture
def store(monkeypatch):
    """The one-slot durable store, seeded so the invalidation half is realistic."""
    return _txn_store(monkeypatch)


@pytest.fixture(autouse=True)
def _venue(monkeypatch):
    import app.services.kalshi_api as kalshi_api

    monkeypatch.setattr(kalshi_api, "KalshiAPIService", _Venue)


async def _batch(session, *, limit=1, after=None):
    """One dry-run call, resumed from the previous call's ``next_cursor``."""
    cursor = after or {}
    return await rail.repair(
        session,
        apply=False,
        limit=limit,
        after_id=cursor.get("after_id"),
        after_date=cursor.get("after_date"),
    )


# =============================================================================
# 1 + 2 — the response carries a RESTORABLE artifact, and it is the banked one
# =============================================================================


class TestTheResponseCarriesTheBackup:
    @pytest.mark.asyncio
    async def test_the_artifact_re_decodes_to_the_responses_own_plan_hash(self, store):
        out = await _batch(_DryRunSession())

        assert out["plan_persisted"] is True
        plan, reason = decode_plan(out["plan_artifact"])
        assert reason == "ok", reason
        # `decode_plan` re-derives the address from the content rather than
        # believing the stored string, so this equality is the whole claim: the
        # captured file can be applied, or read back to undo, on its own terms.
        assert plan.plan_hash == out["plan_hash"]

    @pytest.mark.asyncio
    async def test_it_is_the_banked_payload_not_a_second_derivation(self, store):
        out = await _batch(_DryRunSession())

        banked = store.payload(rail.PLAN_IDENTITY)
        assert banked is not None
        assert out["plan_artifact"] == banked
        assert out["plan_artifact"]["schema"] == APPLY_PLAN_SCHEMA

    @pytest.mark.asyncio
    async def test_every_planned_leg_carries_its_verdict_and_prior_state(self, store):
        out = await _batch(_DryRunSession())

        legs = {leg["leg_id"]: leg for leg in out["plan_artifact"]["legs"]}
        assert sorted(legs) == out["plan_leg_ids"] == [1, 2]
        for leg_id, leg in legs.items():
            assert leg["verdict"] == _EXPECTED_VERDICTS[leg_id]
            assert leg["verdict"] in WRITING_VERDICTS
            assert leg["expected_is_winner"] is False
            assert leg["expected_source"] == REPAIRABLE_SOURCE

    @pytest.mark.asyncio
    async def test_the_leg_ids_alone_cannot_separate_the_two_arms(self, store):
        """Why the ids already in the response are not enough.

        Both arms are in one batch and ``plan_leg_ids`` is a flat list, so the
        undo cannot be written from it: the restore rows need a different
        statement from the retraction rows, and nothing outside
        ``plan_artifact`` says which is which.
        """
        out = await _batch(_DryRunSession())

        verdicts = {leg["verdict"] for leg in out["plan_artifact"]["legs"]}
        assert verdicts == {"restore_winner", "retract_fabricated"}
        flat = {k: v for k, v in out.items() if k != "plan_artifact"}
        assert not any(
            isinstance(v, list)
            and v
            and isinstance(v[0], dict)
            and "verdict" in v[0]
            and {d.get("leg_id") for d in v} >= set(out["plan_leg_ids"])
            for v in flat.values()
        ), "a second per-leg verdict list would make this test's premise false"


# =============================================================================
# 3 — the failure this exists for: batch two overwrites batch one
# =============================================================================


class TestBatchTwoDestroysBatchOnesOnlyOtherCopy:
    @pytest.mark.asyncio
    async def test_the_slot_holds_only_the_latest_batch(self, store):
        session = _DryRunSession()

        first = await _batch(session)
        second = await _batch(session, after=first["next_cursor"])

        # Two distinct batches, each with work.
        assert first["plan_leg_ids"] == [1, 2]
        assert second["plan_leg_ids"] == [4, 5]
        assert first["plan_hash"] != second["plan_hash"]

        # ONE slot: what the apply would load is batch two, and batch one's
        # reviewed plan is gone from the store entirely.
        banked, reason = await rail._load_plan()
        assert reason == "ok"
        assert banked.plan_hash == second["plan_hash"]
        assert list(banked.leg_ids) == [4, 5]

    @pytest.mark.asyncio
    async def test_the_captured_batch_one_response_survives_that(self, store):
        session = _DryRunSession()

        captured = await _batch(session)  # the operator's batchN-plan.json
        await _batch(session, after=captured["next_cursor"])

        # The store can no longer answer "what did batch one restore?" ...
        banked, _ = await rail._load_plan()
        assert 1 not in banked.leg_ids

        # ... and the captured response still can, in the form the undo needs.
        recovered, reason = decode_plan(captured["plan_artifact"])
        assert reason == "ok"
        assert recovered.plan_hash == captured["plan_hash"]
        restore_ids = sorted(
            leg.leg_id for leg in recovered.legs if leg.verdict == "restore_winner"
        )
        assert restore_ids == [1]


# =============================================================================
# 4 — why the restore arm cannot be recovered from the database instead
# =============================================================================


class TestTheRestoreArmLeavesNoMarker:
    @pytest.mark.asyncio
    async def test_a_restored_leg_is_indistinguishable_from_an_untouched_winner(
        self, monkeypatch
    ):
        """The retraction arm stamps itself; the restore arm does not.

        Row 9 is seeded as a leg the repair never touches, already carrying the
        exact state a restore produces. After the apply, row 1 and row 9 are the
        same row state — so no post-hoc query over ``futures_outcomes`` can tell
        the repaired one from the one that was always right.
        """
        _txn_store(monkeypatch)
        plan = build_plan(
            [
                PlannedLeg(
                    1, 100, "restore_winner", False, REPAIRABLE_SOURCE, "KX-A-T1"
                ),
                PlannedLeg(
                    2, 100, "retract_fabricated", False, REPAIRABLE_SOURCE, "KX-A-T2"
                ),
            ]
        )

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)

        session = _UndoSession(
            [
                {"id": 1, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE},
                {"id": 2, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE},
                {"id": 9, "is_winner": True, "resolution_source": REPAIRABLE_SOURCE},
            ]
        )
        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)
        assert out["legs_written"] == 2

        def _state(row):
            return {k: v for k, v in row.items() if k not in ("id", "last_updated")}

        restored, untouched = _state(session.rows[1]), _state(session.rows[9])
        assert restored == untouched, (
            "if the GRADES ever differ the restore arm has grown a marker and "
            "the receipt stops being the only way back"
        )
        # `last_updated` does move — that is CAL-P1008-R2's version stamp, and
        # it is deliberately NOT a marker you can query for: its value is a
        # timestamp nothing but the receipt knows. It tells a restore holding
        # the receipt whether the row is still the one the apply left; it
        # cannot tell anyone which rows the repair touched.
        assert session.rows[1]["last_updated"] != session.rows[9].get("last_updated")
        # The retraction arm, by contrast, names itself in the row.
        assert session.rows[2]["resolution_source"] == RETRACTION_SOURCE
        assert RETRACTION_SOURCE != REPAIRABLE_SOURCE

    def test_both_writing_verdicts_require_the_same_prior_state(self):
        """The pre-image is a rail-wide constant, so it is not what is missing.

        Driven through the shipping classifier over every combination it can
        see, rather than asserted about the fixture: a writing verdict is only
        reachable from ``(is_winner=False, api_settlement)``. That is why the
        gap is the per-leg VERDICT and not the per-leg prior values, and why the
        undo statement can hard-code the state it restores to.
        """
        seen = set()
        for is_winner in (True, False):
            for source in (REPAIRABLE_SOURCE, RETRACTION_SOURCE, "espn", None):
                for status in ("finalized", "settled", None):
                    for result in ("yes", "no", "scalar", "", None):
                        for present in (True, False):
                            verdict = classify_leg(
                                is_winner,
                                source,
                                status,
                                result,
                                present_at_venue=present,
                            )
                            if verdict in WRITING_VERDICTS:
                                seen.add((is_winner, source))
        assert seen == {(False, REPAIRABLE_SOURCE)}


# =============================================================================
# CAL-P1008-R / CERT-965 — the undo is BANKED before the write and RUNS after it
#
# CERT-965 blocked the first CAL-P1008 branch for the right reason: handing the
# plan back on the response makes the undo capturable, but capture is then an
# operator step, and an undo that exists only if a human remembered to save a
# file is the same hole one door down. The bar is a backup WRITTEN FIRST and a
# restore that RUNS.
# =============================================================================


class _UndoSession(_CASSession):
    """PostgreSQL's UPDATE semantics for all FOUR statements this rail emits.

    The p062 session models only the two the APPLY emits and treats anything
    else as a non-match — which would have let every restore assertion pass for
    the wrong reason (0 rows, no error). It also does not model ``last_updated``
    at all, and that column is now the version CERT-970's fix turns on.

    **Both the SET list and the WHERE clause are read out of the SQL**, never
    reproduced from the params. A first version of this class checked
    ``params["repairable"]`` whichever predicate the statement actually carried,
    and deleting the source guard from the shipping SQL left all 19 tests green
    — the test file had quietly grown a second copy of the guard it was supposed
    to be certifying (C-CERT-1852 finding 5, one level down). Deleting a clause
    from a statement must delete it here too, or these tests certify nothing.
    """

    #: Each recognised WHERE clause, and the row predicate it means.
    _CLAUSES = (
        ("AND is_winner = true", lambda row, p: row["is_winner"] is True),
        (
            "AND is_winner = :prior_winner",
            lambda row, p: row["is_winner"] == p["prior_winner"],
        ),
        (
            "AND resolution_source IS NOT DISTINCT FROM :prior_source",
            lambda row, p: row["resolution_source"] == p["prior_source"],
        ),
        (
            "AND resolution_source IS NOT DISTINCT FROM :repairable",
            lambda row, p: row["resolution_source"] == p["repairable"],
        ),
        (
            "AND resolution_source IS NOT DISTINCT FROM :retraction",
            lambda row, p: row["resolution_source"] == p["retraction"],
        ),
        (
            "AND last_updated = :applied_version",
            lambda row, p: row.get("last_updated") == p["applied_version"],
        ),
    )

    #: Each recognised SET assignment, and the new value it writes.
    _SETTERS = (
        ("SET is_winner = true", "is_winner", lambda p: True),
        ("SET is_winner = :prior_winner", "is_winner", lambda p: p["prior_winner"]),
        (
            "resolution_source = 'api_settlement'",
            "resolution_source",
            lambda p: REPAIRABLE_SOURCE,
        ),
        (
            "SET resolution_source = :retraction",
            "resolution_source",
            lambda p: p["retraction"],
        ),
        (
            "SET resolution_source = :prior_source",
            "resolution_source",
            lambda p: p["prior_source"],
        ),
        (
            "last_updated = :applied_version",
            "last_updated",
            lambda p: p["applied_version"],
        ),
        (
            "last_updated = :restored_version",
            "last_updated",
            lambda p: p["restored_version"],
        ),
    )

    def __init__(self, rows) -> None:
        super().__init__(rows)
        #: Durable envelopes staged in this transaction, not yet committed.
        self.pending_durable = []
        self._committed_rows = copy.deepcopy(self.rows)
        self.durable_store = _CURRENT_STORE

    async def commit(self):
        await super().commit()
        self._committed_rows = copy.deepcopy(self.rows)
        for env in self.pending_durable:
            self.durable_store.rows[env.identity] = env
        self.pending_durable = []

    async def rollback(self):
        await super().rollback()
        # Uncommitted row changes AND uncommitted durable writes both vanish.
        self.rows = copy.deepcopy(self._committed_rows)
        self.pending_durable = []

    @staticmethod
    def _halves(sql):
        """(set_clause, where_clause). Split first, so neither half can read the
        other's text — `SET last_updated = :applied_version` and
        `AND last_updated = :applied_version` are the same substring."""
        head, _, where = sql.partition("WHERE")
        return head, where

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "UPDATE futures_outcomes" not in sql:
            return await super().execute(stmt, params)
        self.statements.append(sql)
        set_half, where_half = self._halves(sql)
        row = self.rows.get(params["id"])
        if row is None or not all(
            pred(row, params)
            for clause, pred in self._CLAUSES
            if clause.removeprefix("AND ") in where_half
        ):
            return _FakeResult(0)
        for marker, column, value in self._SETTERS:
            if marker.removeprefix("SET ") in set_half:
                row[column] = value(params)
        return _FakeResult(1)


def _plan(*legs):
    """A plan from `(leg_id, market_id, verdict)` triples.

    Prior state is the rail-wide constant proved above, so it is not a knob
    here: a fixture free to choose it could describe a plan the classifier
    cannot produce.
    """
    return build_plan(
        [
            PlannedLeg(
                leg_id, market_id, verdict, False, REPAIRABLE_SOURCE, f"KX-T{leg_id}"
            )
            for leg_id, market_id, verdict in legs
        ]
    )


def _row(leg_id, *, is_winner=False, source=REPAIRABLE_SOURCE):
    return {"id": leg_id, "is_winner": is_winner, "resolution_source": source}


def _graded(row):
    """The row's GRADE, without the version column either side stamps.

    `last_updated` moving is the point of the fix, not a regression, so the
    assertions about what a restore put back must not read it.
    """
    return {k: v for k, v in row.items() if k != "last_updated"}


async def _apply(monkeypatch, plan, session):
    async def _load():
        return plan, "ok"

    monkeypatch.setattr(rail, "_load_plan", _load)
    return await rail.repair(session, apply=True, plan_hash=plan.plan_hash)


class TestTheReceiptIsBankedBeforeTheWrite:
    @pytest.mark.asyncio
    async def test_the_apply_banks_a_per_plan_receipt(self, monkeypatch):
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])

        out = await _apply(monkeypatch, plan, session)

        assert out["legs_written"] == 2
        banked = store.payload(rail.receipt_identity(plan.plan_hash))
        assert banked is not None
        recovered, reason = decode_plan(banked)
        assert reason == "ok"
        assert recovered.plan_hash == plan.plan_hash
        # ...and the response tells the operator where it is and how to run it.
        assert out["undo"]["receipt_identity"] == rail.receipt_identity(plan.plan_hash)
        assert plan.plan_hash in out["undo"]["apply"]

    @pytest.mark.asyncio
    async def test_an_apply_that_cannot_bank_the_receipt_writes_nothing(
        self, monkeypatch
    ):
        """Ordering is the guarantee, so prove the refusal, not just the order.

        A receipt banked for rows that were never written is harmless — the
        restore's compare-and-set finds nothing to reverse. Rows written with no
        receipt are the unrecoverable state. So the apply must refuse.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        store.forced_status[rail.receipt_identity(plan.plan_hash)] = "rejected"
        session = _UndoSession([_row(1)])

        out = await _apply(monkeypatch, plan, session)

        assert out["success"] is False
        assert out["refused"] == ["UNDO_RECEIPT_NOT_BANKED"]
        assert session.updates() == []
        assert session.rows[1] == _row(1), "the row must be untouched"

    @pytest.mark.asyncio
    async def test_the_receipt_is_per_plan_so_batches_do_not_collide(self, monkeypatch):
        """The failure CERT-965's repair exists for, in one assertion.

        `PLAN_IDENTITY` is one slot; a receipt address is derived from the
        plan's own content, so two batches occupy two addresses.
        """
        store = _txn_store(monkeypatch)
        one = _plan((1, 100, "restore_winner"))
        two = _plan((4, 200, "restore_winner"))
        assert one.plan_hash != two.plan_hash

        await _apply(monkeypatch, one, _UndoSession([_row(1)]))
        await _apply(monkeypatch, two, _UndoSession([_row(4)]))

        assert store.payload(rail.receipt_identity(one.plan_hash)) is not None
        assert store.payload(rail.receipt_identity(two.plan_hash)) is not None
        assert rail.receipt_identity(one.plan_hash) != rail.receipt_identity(
            two.plan_hash
        )


class TestTheRestoreRuns:
    @pytest.mark.asyncio
    async def test_the_dry_run_reports_both_arms_and_writes_nothing(self, monkeypatch):
        _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])
        await _apply(monkeypatch, plan, session)
        before = {k: dict(v) for k, v in session.rows.items()}

        out = await rail.restore(session, apply=False, plan_hash=plan.plan_hash)

        assert out["measured"] is True and out["apply"] is False
        assert out["legs_would_reverse"] == 2
        assert out["by_arm"] == {"restore_winner": 1, "retract_fabricated": 1}
        assert {k: dict(v) for k, v in session.rows.items()} == before

    @pytest.mark.asyncio
    async def test_a_missing_receipt_refuses_rather_than_reporting_nothing_to_undo(
        self, monkeypatch
    ):
        """Gotcha #53 on the undo path: an unreadable receipt is not an absence."""
        _txn_store(monkeypatch)
        out = await rail.restore(
            _UndoSession([]), apply=True, plan_hash="deadbeef-not-a-plan"
        )
        assert out["success"] is False
        assert out["measured"] is False
        assert out["refused"]

    @pytest.mark.asyncio
    async def test_no_plan_hash_is_refused_by_name(self, monkeypatch):
        _txn_store(monkeypatch)
        out = await rail.restore(_UndoSession([]), apply=True)
        assert out["refused"] == ["PLAN_HASH_REQUIRED"]
        assert out["success"] is False


class TestTheCatchingTest:
    """CERT-965's named catching test, in one case.

    Apply two batches, overwrite the plan slot, restore batch one, and preserve
    a concurrent change. Every clause is asserted; none of it is arranged by
    reaching into the store.
    """

    @pytest.mark.asyncio
    async def test_two_batches_then_restore_batch_one_only(self, monkeypatch):
        store = _txn_store(monkeypatch)

        # --- batch one: one leg per arm, plus a leg something else will move --
        one = _plan(
            (1, 100, "restore_winner"),
            (2, 100, "retract_fabricated"),
            (3, 100, "restore_winner"),
        )
        session = _UndoSession([_row(1), _row(2), _row(3)])
        applied_one = await _apply(monkeypatch, one, session)
        assert applied_one["legs_written"] == 3

        # --- batch two: overwrites PLAN_IDENTITY, the single slot -------------
        two = _plan((4, 200, "restore_winner"))
        session.rows[4] = _row(4)
        applied_two = await _apply(monkeypatch, two, session)
        assert applied_two["legs_written"] == 1

        banked_plan, _ = await rail._load_plan()
        assert banked_plan.plan_hash == two.plan_hash, "the plan slot is overwritten"
        assert 1 not in banked_plan.leg_ids

        # --- a concurrent change to one of batch one's rows -------------------
        # A live grader replaces the restored winner with a real result. The
        # restore must leave this alone: it is no longer the row the apply left.
        session.rows[3] = {
            "id": 3,
            "is_winner": True,
            "resolution_source": "espn",
        }
        untouched = dict(session.rows[3])

        # --- restore batch ONE, by its own plan_hash --------------------------
        out = await rail.restore(session, apply=True, plan_hash=one.plan_hash)

        assert out["measured"] is True
        assert sorted(out["reversed_leg_ids"]) == [1, 2]
        assert out["winners_unrestored"] == 1
        assert out["retractions_undone"] == 1

        # the reversed rows are back to the exact pre-apply state
        assert _graded(session.rows[1]) == _row(1)
        assert _graded(session.rows[2]) == _row(2)

        # the concurrently-changed row is PRESERVED, and named rather than silent
        assert session.rows[3] == untouched  # including its version
        assert [d["leg_id"] for d in out["concurrent_drift"]] == [3]
        assert out["concurrent_drift"][0]["verdict"] == "restore_winner"

        # every leg the receipt named was ATTEMPTED — reversed or reported
        assert out["attempted_leg_ids_equal_receipt"] is True

        # batch two is untouched by batch one's restore, and still has its own
        # receipt to be undone from
        assert _graded(session.rows[4]) == {
            "id": 4,
            "is_winner": True,
            "resolution_source": REPAIRABLE_SOURCE,
        }
        assert store.payload(rail.receipt_identity(two.plan_hash)) is not None

    @pytest.mark.asyncio
    async def test_restoring_twice_reverses_nothing_the_second_time(self, monkeypatch):
        """The restore is not re-runnable into a double-undo.

        After the first restore the rows are no longer in the post-apply state,
        so the compare-and-set finds nothing — reported as drift, not as work.
        """
        _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])
        await _apply(monkeypatch, plan, session)

        first = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)
        after_first = {k: dict(v) for k, v in session.rows.items()}
        second = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        assert first["legs_reversed"] == 2
        assert second["legs_reversed"] == 0
        assert second["concurrent_drift_count"] == 2
        assert {k: dict(v) for k, v in session.rows.items()} == after_first


class TestTheRestoreIsRegisteredAndCannotReDerive:
    def test_the_endpoint_exists_and_the_docstring_list_names_it(self):
        from app.routes import admin_repairs

        assert admin_repairs._REPAIRS["kalshi-fabricated-loss-restore"] == (
            "app.tasks.repair_kalshi_fabricated_loss",
            "restore",
        )
        assert "kalshi-fabricated-loss-restore" in admin_repairs.__doc__

    def test_the_dispatcher_can_call_it_with_the_params_it_declares(self):
        import inspect

        params = inspect.signature(rail.restore).parameters
        # `apply` is passed POSITIONALLY by the dispatcher (`fn(db, apply, **extra)`),
        # so it must not be keyword-only, and `plan_hash` must be declared by name
        # or the dispatcher silently drops it.
        assert params["apply"].kind is not inspect.Parameter.KEYWORD_ONLY
        assert "plan_hash" in params

    def test_the_restore_asks_the_venue_nothing(self):
        import inspect

        src = inspect.getsource(rail.restore)
        for forbidden in ("KalshiAPIService", "_fetch_venue", "classify_", "_WORK_SQL"):
            assert (
                forbidden not in src
            ), f"the restore must re-derive nothing — found {forbidden}"


# =============================================================================
# CAL-P1008-R2 / CERT-970 — a same-valued concurrent grade survives, both ways
#
# CERT-970's specimen and its required catching tests. The two cases are
# genuinely different and only one of them is a state comparison:
#
#   BEFORE a skipped apply — a concurrent writer puts the row in the post-apply
#     state, so the apply's CAS skips it. A restore bound to the PLAN would find
#     its predicate satisfied and reverse a write it never made.
#   AFTER a successful apply — the apply writes the row, then a concurrent
#     writer regrades it to the SAME values. No comparison of state can see the
#     difference; only the version the apply stamped can.
# =============================================================================


class TestASameValuedConcurrentGradeSurvives:
    @pytest.mark.asyncio
    async def test_before_a_skipped_apply(self, monkeypatch):
        """The exact CERT-970 reproduction."""
        _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])

        # A grader legitimately declares leg 1 a winner between plan and apply,
        # landing on exactly the values a successful apply would have produced.
        session.rows[1] = {
            "id": 1,
            "is_winner": True,
            "resolution_source": REPAIRABLE_SOURCE,
            "last_updated": "a-real-graders-write",
        }
        theirs = dict(session.rows[1])

        applied = await _apply(monkeypatch, plan, session)
        assert applied["legs_written"] == 1, "leg 1 must be SKIPPED, not written"
        assert [d["leg_id"] for d in applied["concurrent_drift"]] == [1]

        out = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        # Leg 1 was never written by this apply, so the restore must not name it
        # at all — not even as drift it considered.
        assert out["reversed_leg_ids"] == [2]
        assert session.rows[1] == theirs, "a real grade was destroyed"

    @pytest.mark.asyncio
    async def test_after_a_successful_apply(self, monkeypatch):
        """The half no state comparison can reach.

        The apply writes the row. A grader then writes the SAME values over it —
        a legitimate re-affirmation that is now their grade, not ours. Values are
        identical; only the version moved.
        """
        _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])

        applied = await _apply(monkeypatch, plan, session)
        assert applied["legs_written"] == 2

        # Same values, different write.
        assert session.rows[1]["is_winner"] is True
        assert session.rows[1]["resolution_source"] == REPAIRABLE_SOURCE
        session.rows[1]["last_updated"] = "a-later-write-with-the-same-values"
        theirs = dict(session.rows[1])

        out = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        assert out["reversed_leg_ids"] == [2]
        assert session.rows[1] == theirs
        assert [d["leg_id"] for d in out["concurrent_drift"]] == [1]
        # ...and it is ATTEMPTED, so the honesty contract still holds.
        assert out["attempted_leg_ids_equal_receipt"] is True

    @pytest.mark.asyncio
    async def test_the_restore_is_bound_to_what_was_written_not_what_was_planned(
        self, monkeypatch
    ):
        """The structural version of the two cases above."""
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(2)])  # leg 1's row does not exist at all

        await _apply(monkeypatch, plan, session)

        # The PLAN receipt still names both legs — it is the pre-image, and it
        # is deliberately not what a restore reads.
        planned, _ = decode_plan(store.payload(rail.receipt_identity(plan.plan_hash)))
        assert list(planned.leg_ids) == [1, 2]

        out = await rail.restore(session, apply=False, plan_hash=plan.plan_hash)
        assert out["leg_ids"] == [2], "the applied receipt holds only what was written"

    @pytest.mark.asyncio
    async def test_a_retry_adds_its_legs_and_an_empty_apply_blanks_nothing(
        self, monkeypatch
    ):
        """The merge rule, which is what makes a partly-applied plan recoverable.

        Leg 1's row is missing on the first apply and appears before the retry.
        The retry must ADD it; and a third apply that writes nothing must not
        erase either.
        """
        _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(2)])

        first = await _apply(monkeypatch, plan, session)
        assert first["legs_written"] == 1

        session.rows[1] = _row(1)
        second = await _apply(monkeypatch, plan, session)
        assert second["legs_written"] == 1

        third = await _apply(monkeypatch, plan, session)
        assert third["legs_written"] == 0

        out = await rail.restore(session, apply=False, plan_hash=plan.plan_hash)
        assert out["leg_ids"] == [1, 2]

    @pytest.mark.asyncio
    async def test_a_receipt_that_cannot_be_staged_rolls_the_whole_apply_back(
        self, monkeypatch
    ):
        """CERT-1858's catching test. The row must be UNCHANGED, not reported.

        An earlier version of this test asserted that an apply which wrote rows
        it could not bank a receipt for said so — ``reversible: false`` — and
        called that the fix. It is not. An honest description of an
        unrecoverable row is not a defence against creating one. The receipt is
        now STAGED in the same transaction as the mutations, so a staging
        failure takes the rows with it.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])
        before = copy.deepcopy(session.rows)
        store.forced_status[rail.applied_identity(plan.plan_hash)] = "rejected"

        out = await _apply(monkeypatch, plan, session)

        assert out["success"] is False
        assert out["measured"] is False
        assert out["refused"] == ["UNDO_RECEIPT_NOT_STAGED"]
        assert out["rolled_back"] is True
        assert out["legs_written"] == 0
        # The rows the compare-and-set matched are back as they were, and this
        # session never committed.
        assert session.rows == before
        assert session.commits == 0
        assert session.pending_durable == []
        # Nothing reached the store either, so there is no half-receipt to
        # mislead a later restore.
        assert store.payload(rail.applied_identity(plan.plan_hash)) is None

    @pytest.mark.asyncio
    async def test_a_staging_failure_with_nothing_written_is_not_a_rollback(
        self, monkeypatch
    ):
        """The other side of it: no rows, no alarm.

        A plan whose legs all drift writes nothing, so there is nothing to
        protect and nothing to roll back. Refusing here would turn a harmless
        no-op into an alarm, and an alarm nobody can act on is how a real one
        gets ignored.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1, is_winner=True)])  # already moved
        store.forced_status[rail.applied_identity(plan.plan_hash)] = "rejected"

        out = await _apply(monkeypatch, plan, session)

        assert out["measured"] is True
        assert out["legs_written"] == 0
        assert out["concurrent_drift_count"] == 1
        assert out.get("rolled_back") is None

    @pytest.mark.asyncio
    async def test_a_restore_refuses_when_only_the_plan_receipt_exists(
        self, monkeypatch
    ):
        """The pre-write receipt is forensics, never a licence to write."""
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        store.forced_status[rail.applied_identity(plan.plan_hash)] = "rejected"
        await _apply(monkeypatch, plan, session)
        before = dict(session.rows[1])

        out = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        assert out["success"] is False
        assert out["measured"] is False
        assert out["refused"] == [REASON_APPLIED_MISSING]
        # ...and it points the operator at the forensic record rather than
        # pretending there is nothing to look at.
        assert out["plan_receipt_identity"] == rail.receipt_identity(plan.plan_hash)
        assert session.rows[1] == before


class TestTheAppliedReceiptIsPure:
    """`build_applied_receipt` / `decode_applied_receipt` — no DB, no clock."""

    def test_the_merge_keeps_the_earliest_record_of_a_leg(self):
        first = build_applied_receipt(
            "h",
            [
                {
                    "leg_id": 1,
                    "market_id": 10,
                    "verdict": "restore_winner",
                    "prior_is_winner": False,
                    "prior_source": "api_settlement",
                    "applied_version": "v1",
                }
            ],
        )
        second = build_applied_receipt(
            "h",
            [
                {
                    "leg_id": 1,
                    "market_id": 10,
                    "verdict": "restore_winner",
                    "prior_is_winner": False,
                    "prior_source": "api_settlement",
                    "applied_version": "v2",
                },
                {
                    "leg_id": 2,
                    "market_id": 10,
                    "verdict": "retract_fabricated",
                    "prior_is_winner": False,
                    "prior_source": "api_settlement",
                    "applied_version": "v2",
                },
            ],
            existing=first,
        )
        by_id = {leg["leg_id"]: leg for leg in second["legs"]}
        assert by_id[1]["applied_version"] == "v1", "a retry cannot rewrite history"
        assert by_id[2]["applied_version"] == "v2"
        assert second["leg_count"] == 2

    def test_an_empty_write_set_leaves_the_receipt_intact(self):
        first = build_applied_receipt(
            "h",
            [
                {
                    "leg_id": 1,
                    "market_id": 10,
                    "verdict": "restore_winner",
                    "prior_is_winner": False,
                    "prior_source": "api_settlement",
                    "applied_version": "v1",
                }
            ],
        )
        assert build_applied_receipt("h", [], existing=first) == first

    def test_a_receipt_from_another_plan_is_refused_by_name(self):
        payload = build_applied_receipt("h", [])
        legs, reason = decode_applied_receipt(
            payload, expected_source_plan_hash="other"
        )
        assert legs is None
        assert reason == REASON_APPLIED_SOURCE_MISMATCH

    def test_a_count_that_disagrees_with_its_list_is_corrupt_not_smaller(self):
        payload = build_applied_receipt(
            "h",
            [
                {
                    "leg_id": 1,
                    "market_id": 10,
                    "verdict": "restore_winner",
                    "prior_is_winner": False,
                    "prior_source": "api_settlement",
                    "applied_version": "v1",
                }
            ],
        )
        payload["leg_count"] = 5
        legs, reason = decode_applied_receipt(payload, expected_source_plan_hash="h")
        assert legs is None
        assert reason == REASON_APPLIED_CORRUPT


# =============================================================================
# CAL-P1008-R4 / CERT-1863 — a status is not a receipt
# =============================================================================


class TestSupersededIsNotBanked:
    """`publish_snapshot_in_txn` answers `superseded` and writes NOTHING.

    For a plan artifact that genuinely means "a good copy exists", which is why
    `_save_plan` accepts it — and copying that judgment here committed rows
    whose undo record did not contain them. The gate is now containment, read
    back from the store, so the status is only ever a note.
    """

    @pytest.mark.asyncio
    async def test_a_superseded_stage_rolls_the_apply_back(self, monkeypatch):
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])
        before = copy.deepcopy(session.rows)
        store.forced_status[rail.applied_identity(plan.plan_hash)] = "superseded"

        out = await _apply(monkeypatch, plan, session)

        assert out["success"] is False
        assert out["refused"] == ["UNDO_RECEIPT_NOT_STAGED"]
        assert out["rolled_back"] is True
        assert out["legs_written"] == 0
        assert session.rows == before
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_a_rival_receipt_at_the_identity_does_not_count_as_ours(
        self, monkeypatch
    ):
        """The production shape of `superseded`: something IS there, and it is
        not this write. Containment is what says so."""
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        before = copy.deepcopy(session.rows)
        identity = rail.applied_identity(plan.plan_hash)
        store.forced_status[identity] = "superseded"
        store.seed(
            identity,
            rail.APPLIED_RECEIPT_SCHEMA,
            build_applied_receipt(
                plan.plan_hash,
                [
                    {
                        "leg_id": 99,
                        "market_id": 100,
                        "verdict": "restore_winner",
                        "prior_is_winner": False,
                        "prior_source": REPAIRABLE_SOURCE,
                        "applied_version": "a-rivals-write",
                    }
                ],
            ),
        )

        out = await _apply(monkeypatch, plan, session)

        assert out["refused"] == ["UNDO_RECEIPT_NOT_STAGED"]
        assert "does not contain this write" in out["applied_receipt_note"]
        assert "superseded" in out["applied_receipt_note"]
        assert session.rows == before
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_a_superseded_stage_whose_row_ALREADY_holds_this_write_is_fine(
        self, monkeypatch
    ):
        """The half that makes containment the right gate rather than a ban.

        A concurrent identical apply banked the same legs at the same versions
        first. Nothing of ours was written, the status is `superseded`, and the
        durable record is nonetheless correct — so refusing on the status alone
        would roll back a repair whose undo genuinely exists.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])

        # Learn the version this apply will stamp by watching the statement it
        # issues, then seed the store as a rival that already banked it.
        captured = {}
        real_execute = session.execute

        async def _spy(stmt, params=None):
            if params and "applied_version" in params:
                captured["v"] = params["applied_version"]
            return await real_execute(stmt, params)

        session.execute = _spy
        store.forced_status[rail.applied_identity(plan.plan_hash)] = "superseded"

        async def _publish_then_seed(db, envelope):
            store.rows[envelope.identity] = envelope
            return {
                "status": "superseded",
                "identity": envelope.identity,
                "generation": envelope.generation,
            }

        import app.services.durable_snapshots as ds

        monkeypatch.setattr(ds, "publish_snapshot_in_txn", _publish_then_seed)

        out = await _apply(monkeypatch, plan, session)

        assert captured, "the apply must have stamped a version"
        assert out["legs_written"] == 1
        assert out["undo"]["applied_receipt_banked"] is True
        assert "superseded" in out["undo"]["applied_receipt_note"]
        assert session.commits == 1


class TestContainmentIsPure:
    LEG = {
        "leg_id": 1,
        "market_id": 10,
        "verdict": "restore_winner",
        "prior_is_winner": False,
        "prior_source": REPAIRABLE_SOURCE,
        "applied_version": "v1",
    }

    def test_a_receipt_holding_the_write_contains_it(self):
        ok, why = applied_receipt_contains(
            build_applied_receipt("h", [self.LEG]),
            expected_source_plan_hash="h",
            written_legs=[self.LEG],
        )
        assert (ok, why) == (True, "ok")

    def test_a_receipt_missing_the_leg_does_not(self):
        ok, why = applied_receipt_contains(
            build_applied_receipt("h", []),
            expected_source_plan_hash="h",
            written_legs=[self.LEG],
        )
        assert ok is False
        assert why.startswith("APPLIED_RECEIPT_MISSING_LEGS")

    def test_the_same_leg_at_a_DIFFERENT_version_does_not(self):
        """Somebody else's write of the same row is not this call's undo."""
        theirs = {**self.LEG, "applied_version": "someone-elses-write"}
        ok, why = applied_receipt_contains(
            build_applied_receipt("h", [theirs]),
            expected_source_plan_hash="h",
            written_legs=[self.LEG],
        )
        assert ok is False
        assert why.startswith("APPLIED_RECEIPT_MISSING_LEGS")

    def test_a_receipt_from_another_plan_does_not(self):
        ok, why = applied_receipt_contains(
            build_applied_receipt("other", [self.LEG]),
            expected_source_plan_hash="h",
            written_legs=[self.LEG],
        )
        assert (ok, why) == (False, REASON_APPLIED_SOURCE_MISMATCH)


# =============================================================================
# CAL-P1009 — the restore joins the invalidation obligation ledger
#
# The apply owes the published curve an invalidation for every row it writes,
# and it carries that debt in ONE durable slot so a crash between the write and
# the invalidation leaves the debt visible. The restore writes the same rows in
# the opposite direction and did not join that ledger at all. Two consequences,
# and the first one stops the drain dead:
#
# 1. An apply whose invalidation failed leaves an OPEN debt naming its plan. Undo
#    it, and the debt survives the undo — so every later page of the drain is
#    refused with OUTSTANDING_INVALIDATION, and the only escape the rail names is
#    to re-apply the plan that was just deliberately undone.
# 2. The slot has one writer's worth of room. A restore banking its own debt
#    without reading first would erase an apply's.
#
# The invalidation is WHOLESALE by construction (it discards the staged cursor
# and the main checkpoint outright), so one proved invalidation genuinely pays
# every outstanding market id — which is why carrying the prior debt into the
# union is the truth here and not a convenience.
# =============================================================================


class TestTheRestoreJoinsTheObligationLedger:
    @pytest.mark.asyncio
    async def test_an_undone_repair_stops_blocking_every_later_page(self, monkeypatch):
        """THE SPECIMEN. Pre-fix the second page is refused, and the refusal's
        own advice is to redo the repair the operator undid."""
        store = _txn_store(monkeypatch)
        store.unreadable[CHECKPOINT_IDENTITY] = "unavailable"  # cannot prove itself

        one = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        applied = await _apply(monkeypatch, one, session)
        assert applied["legs_written"] == 1
        assert applied["invalidation_obligation"]["discharged"] is False

        store.unreadable.pop(CHECKPOINT_IDENTITY)  # the store recovers
        undone = await rail.restore(session, apply=True, plan_hash=one.plan_hash)
        assert undone["legs_reversed"] == 1
        assert undone["success"] is True

        # The next page of the drain — a DIFFERENT plan, nothing to do with the
        # one that was undone.
        two = _plan((4, 200, "retract_fabricated"))
        out = await _apply(monkeypatch, two, _UndoSession([_row(4)]))

        assert "refused" not in out, out.get("reason")
        assert out["legs_written"] == 1

    @pytest.mark.asyncio
    async def test_a_prior_debt_is_carried_rather_than_overwritten(self, monkeypatch):
        """The one slot must never lose an id to the restore's own record."""
        store = _txn_store(monkeypatch)

        one = _plan((1, 100, "restore_winner"))
        s1 = _UndoSession([_row(1)])
        assert (await _apply(monkeypatch, one, s1))["success"] is True

        # A later page's invalidation fails: an OPEN debt on market 200.
        store.unreadable[CHECKPOINT_IDENTITY] = "unavailable"
        two = _plan((4, 200, "retract_fabricated"))
        second = await _apply(monkeypatch, two, _UndoSession([_row(4)]))
        assert second["invalidation_obligation"]["discharged"] is False
        assert obligation_market_ids(store.payload(rail.OBLIGATION_IDENTITY)) == [200]

        # Undo page ONE while that debt is still open and still unpayable.
        undone = await rail.restore(s1, apply=True, plan_hash=one.plan_hash)

        banked = store.payload(rail.OBLIGATION_IDENTITY)
        assert obligation_market_ids(banked) == [100, 200], "the slot dropped a debt"
        assert banked["owner"] == rail.OBLIGATION_OWNER_RESTORE
        assert undone["invalidation_obligation"]["carried_prior_debt"] is True
        assert undone["success"] is False

    @pytest.mark.asyncio
    async def test_an_unreadable_ledger_refuses_before_reversing_anything(
        self, monkeypatch
    ):
        """UNKNOWN is not 'no debt' — and here it is also 'no room to bank mine'."""
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])
        await _apply(monkeypatch, plan, session)
        before = copy.deepcopy(session.rows)

        store.unreadable[rail.OBLIGATION_IDENTITY] = "unavailable"
        out = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        assert out["refused"] == ["OBLIGATION_LEDGER_UNREADABLE"]
        assert out["success"] is False
        assert session.rows == before, "a refusal that had already written"

    @staticmethod
    async def _unpaid_restore(monkeypatch):
        """Apply, then undo, with the undo's invalidation unable to prove itself.

        The state the next two tests are each about one half of: rows reversed,
        an OPEN debt sitting in the shared slot, and the debt made by the
        RESTORE rather than by the apply.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        await _apply(monkeypatch, plan, session)

        store.unreadable[CHECKPOINT_IDENTITY] = "unavailable"  # RESTORE cannot pay
        undone = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)
        assert undone["legs_reversed"] == 1 and undone["success"] is False
        return store, plan

    @pytest.mark.asyncio
    async def test_an_unpaid_restores_record_says_a_RESTORE_pays_it(self, monkeypatch):
        store, _ = await self._unpaid_restore(monkeypatch)

        banked = store.payload(rail.OBLIGATION_IDENTITY)
        assert obligation_retry_instruction(banked) == RESTORE_DISCHARGES
        assert "Do NOT re-apply" in banked["note"]

    @pytest.mark.asyncio
    async def test_the_reapply_of_an_undone_plan_is_refused(self, monkeypatch):
        """Re-applying that same plan_hash WOULD pay the curve — by rewriting the
        repair the restore just undid. That is not a retry's decision to make."""
        store, plan = await self._unpaid_restore(monkeypatch)

        again = await _apply(monkeypatch, plan, _UndoSession([_row(1)]))

        assert again["refused"] == ["OUTSTANDING_INVALIDATION"]
        assert again["outstanding_obligation"]["owner"] == rail.OBLIGATION_OWNER_RESTORE
        assert again["outstanding_obligation"]["discharged_by"] == RESTORE_DISCHARGES

    @pytest.mark.asyncio
    async def test_re_running_the_restore_pays_a_debt_it_cannot_reverse_again(
        self, monkeypatch
    ):
        """The retry handle the ledger exists to provide, on the undo path.

        Nothing is left to reverse — the rows already moved — so the ONLY record
        of what the curve is owed is the banked obligation. Pre-fix there is no
        such record and the market ids are gone with the response.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        await _apply(monkeypatch, plan, session)

        store.unreadable[CHECKPOINT_IDENTITY] = "unavailable"
        first = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)
        assert first["legs_reversed"] == 1 and first["success"] is False

        store.unreadable.pop(CHECKPOINT_IDENTITY)
        second = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        assert second["legs_reversed"] == 0, "there is nothing left to reverse"
        # The ids come from the LEDGER, not from this call's (empty) reversals.
        # Without the banked debt they would be `[]`, which the invalidation
        # answers `nothing_written` — the false green this ledger exists to stop.
        assert second["invalidation_obligation"]["market_ids"] == [100]
        assert second["calibration_invalidation"]["status"] == "invalidated"
        assert second["invalidation_obligation"]["discharged"] is True


# =============================================================================
# CAL-P1009-R / CERT-1872 — the debt COMMITS WITH THE ROWS, or neither does
#
# The first presentation banked the restore's OPEN debt after the commit that
# reversed the rows. Between those two steps there is an interval, and CERT-1872
# reproduced what is in the store if the process is lost inside it: the reversed
# outcome is permanent, the published calibration curve is stale, and NOTHING
# durable names what would pay it. The retry then reverses zero rows, owes no
# market ids, and reads a slot still holding the previous, discharged record —
# the retry handle the whole ledger exists to provide is simply absent.
#
# So the debt is staged in the SAME transaction as the reversals, gated on
# containment read back from the store, and the caller commits once. That is
# CERT-1858's answer for the undo receipt, one slot over, for the same reason:
# reporting an unrecoverable state honestly is not a substitute for not creating
# it. It applies to BOTH writers of the one slot — the apply had the identical
# window, and closing only the undo's half would leave the class open.
# =============================================================================


class _ProcessLost(RuntimeError):
    """The dyno is gone. Nothing after the commit runs — not the obligation
    publish, not the invalidation, not the response."""


class _CrashOnCommitSession(_UndoSession):
    """Commits, and then the process is lost. The window CERT-1872 named.

    The commit is REAL — rows and anything staged in the transaction land — and
    execution stops the instant afterwards. Nothing that the old code did after
    the commit can be reached, which is precisely what makes it able to tell the
    two orderings apart.
    """

    async def commit(self):
        await super().commit()
        raise _ProcessLost("process lost immediately after commit")


class TestTheDebtCommitsWithTheRowsOrNeitherDoes:
    @pytest.mark.asyncio
    async def test_a_process_loss_the_instant_after_the_commit_leaves_the_debt(
        self, monkeypatch
    ):
        """THE CATCHING TEST. Reversed row and OPEN debt, or neither.

        The only route to the slot in the first half is the reversal's own
        transaction: standalone publishes are made no-ops, so a debt found in
        the store afterwards can only have arrived with the rows. Pre-fix the
        slot still holds the apply's DISCHARGED record and market 100's reversal
        is owed by nothing.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        await _apply(monkeypatch, plan, session)
        assert store.payload(rail.OBLIGATION_IDENTITY)["state"] == "discharged"

        # Nothing may reach the slot except through the transaction that
        # reverses the row: a standalone publish now answers `ok` and writes
        # nothing (C-CERT-1852-R2 specimen one, used here as a fence).
        store.no_op.add(rail.OBLIGATION_IDENTITY)

        crashed = _CrashOnCommitSession(list(session.rows.values()))
        with pytest.raises(_ProcessLost):
            await rail.restore(crashed, apply=True, plan_hash=plan.plan_hash)

        # The reversal is permanent...
        assert crashed.rows[1]["is_winner"] is False, "the row did not reverse"
        # ...and the debt it created is IN the store, open, and says a RESTORE
        # pays it.
        banked = store.payload(rail.OBLIGATION_IDENTITY)
        assert banked["state"] == "open", "the reversal committed with no debt"
        assert obligation_market_ids(banked) == [100]
        assert banked["owner"] == rail.OBLIGATION_OWNER_RESTORE
        assert obligation_retry_instruction(banked) == RESTORE_DISCHARGES

        # RECOVERY. Nothing is left to reverse, so the market ids can come from
        # one place only — the record that survived the loss.
        store.no_op.discard(rail.OBLIGATION_IDENTITY)
        retry = await rail.restore(
            _UndoSession(list(crashed.rows.values())),
            apply=True,
            plan_hash=plan.plan_hash,
        )

        assert retry["legs_reversed"] == 0
        assert retry["invalidation_obligation"]["market_ids"] == [100]
        assert retry["calibration_invalidation"]["status"] == "invalidated"
        assert retry["invalidation_obligation"]["discharged"] is True
        assert store.payload(rail.OBLIGATION_IDENTITY)["state"] == "discharged"
        assert retry["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["error", "superseded"])
    async def test_a_debt_that_cannot_be_staged_reverses_nothing(
        self, monkeypatch, status
    ):
        """The other half of "or neither".

        ``superseded`` is the one that matters most: the durable layer answers
        it when a newer generation already sits at the identity, and it writes
        NOTHING (CERT-1863). A rail that read the status as success would commit
        reversals against somebody else's record.
        """
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 100, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2)])
        await _apply(monkeypatch, plan, session)
        before = copy.deepcopy(session.rows)
        discharged_by_the_apply = copy.deepcopy(store.payload(rail.OBLIGATION_IDENTITY))

        store.forced_status[rail.OBLIGATION_IDENTITY] = status
        out = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        assert out["refused"] == ["INVALIDATION_DEBT_NOT_STAGED"]
        assert out["legs_reversed"] == 0 and out["rolled_back"] is True
        assert out["success"] is False
        assert session.rows == before, "rows reversed with no durable debt"
        assert store.payload(rail.OBLIGATION_IDENTITY) == discharged_by_the_apply

    @pytest.mark.asyncio
    async def test_a_staging_failure_is_not_paid_by_the_applys_own_open_record(
        self, monkeypatch
    ):
        """Containment is about MY record, not about *a* record.

        The slot may already hold an OPEN debt for this very plan_hash — the
        apply's, if its invalidation never discharged — naming the very same
        market. Reading that as this restore's staged debt would commit the
        reversals under a record whose instruction is to RE-APPLY the plan,
        which pays the curve by redoing the repair the reversals just undid.
        """
        store = _txn_store(monkeypatch)
        store.unreadable[CHECKPOINT_IDENTITY] = "unavailable"  # the apply cannot pay
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        applied = await _apply(monkeypatch, plan, session)
        assert applied["invalidation_obligation"]["discharged"] is False

        owed_by_the_apply = copy.deepcopy(store.payload(rail.OBLIGATION_IDENTITY))
        assert owed_by_the_apply["owner"] == rail.OBLIGATION_OWNER_APPLY
        assert obligation_market_ids(owed_by_the_apply) == [100]
        before = copy.deepcopy(session.rows)

        store.unreadable.pop(CHECKPOINT_IDENTITY)  # the store recovers
        store.forced_status[rail.OBLIGATION_IDENTITY] = "error"  # ...but the slot won't take mine
        out = await rail.restore(session, apply=True, plan_hash=plan.plan_hash)

        assert out["refused"] == ["INVALIDATION_DEBT_NOT_STAGED"]
        assert "OBLIGATION_OWNER_IS" in out["obligation_note"]
        assert session.rows == before, "reversed under somebody else's instruction"
        assert store.payload(rail.OBLIGATION_IDENTITY) == owed_by_the_apply

    @pytest.mark.asyncio
    async def test_the_apply_stages_its_debt_with_its_rows_too(self, monkeypatch):
        """The same window, on the other writer of the one slot.

        The ledger exists because the APPLY commits before it invalidates, so
        closing the restore's half and leaving this one open would fix the
        instance and not the class.
        """
        store = _txn_store(monkeypatch)
        store.no_op.add(rail.OBLIGATION_IDENTITY)  # only the transaction may write it
        plan = _plan((1, 100, "restore_winner"))

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)
        crashed = _CrashOnCommitSession([_row(1)])
        with pytest.raises(_ProcessLost):
            await rail.repair(crashed, apply=True, plan_hash=plan.plan_hash)

        assert crashed.rows[1]["is_winner"] is True, "the row did not apply"
        banked = store.payload(rail.OBLIGATION_IDENTITY)
        assert banked["state"] == "open", "the apply committed with no debt"
        assert obligation_market_ids(banked) == [100]
        assert banked["owner"] == rail.OBLIGATION_OWNER_APPLY
        assert obligation_retry_instruction(banked) == REAPPLY_DISCHARGES

    @pytest.mark.asyncio
    async def test_an_unstageable_debt_writes_no_rows_in_the_apply_either(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        store.forced_status[rail.OBLIGATION_IDENTITY] = "error"
        plan = _plan((1, 100, "restore_winner"))

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)
        session = _UndoSession([_row(1)])
        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["refused"] == ["INVALIDATION_DEBT_NOT_STAGED"]
        assert out["legs_written"] == 0 and out["success"] is False
        assert session.rows[1]["is_winner"] is False, "a row written with no debt"
        assert store.payload(rail.OBLIGATION_IDENTITY) is None


class TestTheDebtContainmentIsPure:
    """One clause of the staging gate per test, driven by a table.

    The rail-level tests above exercise the gate through a store, which can only
    reach the combinations a store can produce; each clause is separately
    load-bearing and each therefore gets a case that only it refuses.
    """

    def _record(self, **over):
        base = new_obligation(
            plan_hash="h",
            market_ids=[100],
            leg_ids=[1],
            owner=rail.OBLIGATION_OWNER_RESTORE,
            retry_instruction=RESTORE_DISCHARGES,
        )
        base.update(over)
        return base

    def _contains(self, raw, **over):
        args = {
            "plan_hash": "h",
            "owner": rail.OBLIGATION_OWNER_RESTORE,
            "market_ids": [100],
            "leg_ids": [1],
        }
        args.update(over)
        return obligation_contains(raw, **args)

    def test_my_own_record_read_back_is_contained(self):
        assert self._contains(self._record()) == (True, "ok")

    def test_a_union_carrying_an_earlier_calls_ids_is_still_contained(self):
        """Containment, not equality: the union may legitimately be wider."""
        wider = self._record(market_ids=[100, 200], leg_ids=[1, 4])
        assert self._contains(wider)[0] is True

    def test_a_discharged_record_is_not_a_debt(self):
        ok, why = self._contains(discharge_obligation(self._record()))
        assert (ok, why) == (False, "OBLIGATION_IN_THE_SLOT_IS_ALREADY_DISCHARGED")

    def test_the_applys_record_for_the_same_plan_is_not_mine(self):
        """Same plan_hash, same market, OPEN — and the wrong instruction."""
        theirs = self._record(owner=rail.OBLIGATION_OWNER_APPLY)
        ok, why = self._contains(theirs)
        assert ok is False and why.startswith("OBLIGATION_OWNER_IS")

    def test_another_plans_record_is_not_mine(self):
        ok, why = self._contains(self._record(plan_hash="other"))
        assert ok is False and why.startswith("OBLIGATION_PLAN_HASH_IS")

    def test_a_record_missing_one_owed_market_is_refused(self):
        ok, why = self._contains(self._record(), market_ids=[100, 200])
        assert (ok, why) == (False, "OBLIGATION_MISSING_MARKET_IDS:[200]")

    def test_a_record_missing_one_owed_leg_is_refused(self):
        ok, why = self._contains(self._record(), leg_ids=[1, 4])
        assert (ok, why) == (False, "OBLIGATION_MISSING_LEG_IDS:[4]")

    def test_a_foreign_schema_is_refused_rather_than_guessed_at(self):
        ok, why = self._contains(self._record(schema="something-else/v9"))
        assert ok is False and why.startswith("OBLIGATION_SCHEMA_IS")

    def test_a_non_record_is_refused(self):
        assert self._contains(None)[0] is False
        assert self._contains("open")[0] is False


class TestTheRetryInstructionIsCarriedNotAssumed:
    """Pure. One slot, two writers, opposite directions."""

    def test_a_record_written_before_the_field_existed_reads_as_the_applys(self):
        assert obligation_retry_instruction({"state": "open"}) == REAPPLY_DISCHARGES
        assert obligation_retry_instruction(None) == REAPPLY_DISCHARGES

    def test_the_two_instructions_are_not_the_same_sentence(self):
        assert RESTORE_DISCHARGES != REAPPLY_DISCHARGES
        assert "re-apply" in REAPPLY_DISCHARGES.lower()
        assert "do not re-apply" in RESTORE_DISCHARGES.lower()
