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

from types import SimpleNamespace

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
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
    build_applied_receipt,
    build_plan,
    decode_applied_receipt,
    decode_plan,
)
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


@pytest.fixture
def store(monkeypatch):
    """The one-slot durable store, seeded so the invalidation half is realistic."""
    return _seeded_store(monkeypatch)


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
        _seeded_store(monkeypatch)
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

        session = _CASSession(
            [
                {"id": 1, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE},
                {"id": 2, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE},
                {"id": 9, "is_winner": True, "resolution_source": REPAIRABLE_SOURCE},
            ]
        )
        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)
        assert out["legs_written"] == 2

        def _state(row):
            return {k: v for k, v in row.items() if k != "id"}

        restored, untouched = _state(session.rows[1]), _state(session.rows[9])
        assert restored == untouched, (
            "if these ever differ the restore arm has grown a marker and the "
            "captured plan stops being the only way back"
        )
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
        store = _seeded_store(monkeypatch)
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
        store = _seeded_store(monkeypatch)
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
        store = _seeded_store(monkeypatch)
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
        _seeded_store(monkeypatch)
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
        _seeded_store(monkeypatch)
        out = await rail.restore(
            _UndoSession([]), apply=True, plan_hash="deadbeef-not-a-plan"
        )
        assert out["success"] is False
        assert out["measured"] is False
        assert out["refused"]

    @pytest.mark.asyncio
    async def test_no_plan_hash_is_refused_by_name(self, monkeypatch):
        _seeded_store(monkeypatch)
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
        store = _seeded_store(monkeypatch)

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
        _seeded_store(monkeypatch)
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
        _seeded_store(monkeypatch)
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
        _seeded_store(monkeypatch)
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
        store = _seeded_store(monkeypatch)
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
        _seeded_store(monkeypatch)
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
    async def test_committed_rows_with_no_applied_receipt_are_not_a_success(
        self, monkeypatch
    ):
        """Rows nothing can reverse are a failure, reported, not left to be found."""
        store = _seeded_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])
        store.forced_status[rail.applied_identity(plan.plan_hash)] = "rejected"

        out = await _apply(monkeypatch, plan, session)

        assert out["legs_written"] == 1
        assert out["undo"]["applied_receipt_banked"] is False
        assert out["undo"]["reversible"] is False
        assert out["success"] is False

    @pytest.mark.asyncio
    async def test_a_restore_refuses_when_only_the_plan_receipt_exists(
        self, monkeypatch
    ):
        """The pre-write receipt is forensics, never a licence to write."""
        store = _seeded_store(monkeypatch)
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
