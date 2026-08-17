"""CAL-P058: the five C-CERT-1852 findings, each with the proof that fails first.

Every class here exists because a specific defect shipped, and every test is
written so that REVERTING the fix turns it red. The certification's sharpest
observation was that a 53-test suite could be green while the attended write
protocol was broken, because the suite only ever asserted on strings in the
source and on a pure classifier. So each proof below drives the thing it claims
to certify:

* finding 1 — a fixture that REPAIRS more than one page and asserts zero rows
  are missed, run against the real cursor helper and the real page predicate;
* finding 2 — the artifact binding, driven through the real ``repair()``
  dispatcher, including apply-without-a-plan and apply-with-a-stale-plan;
* finding 3 — the compare-and-set, with a row deliberately moved between plan
  and write, asserting the write is SKIPPED and NAMED;
* finding 4 — the invalidation is invoked by the apply path, its count is
  reported, and a failed invalidation forces ``success: false``;
* finding 5 — the specimen replay entering through the SAME mapper production
  uses, plus a mutation test that a positional mapper fails it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.kalshi_fabricated_loss import (
    REPAIRABLE_SOURCE,
    RETRACTION_SOURCE,
    WRITING_VERDICTS,
    map_venue_by_ticker,
    plan_market_legs,
)
from app.utils.repair_apply_plan import (
    REASON_CONCURRENT_DRIFT,
    REASON_CURSOR_SKIP,
    REASON_OUTSIDE_APPROVED,
    REASON_PLAN_CORRUPT,
    REASON_PLAN_HASH_MISMATCH,
    REASON_PLAN_MISSING,
    ApplyPlan,
    PlannedLeg,
    bind_apply,
    build_plan,
    cursor_skips_unprocessed,
    decode_plan,
    evaluate_repair_contract,
    keyset_after,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _obligation_ledger(monkeypatch):
    """CAL-P062 plumbing, not a weakening of anything asserted below.

    C-CERT-1852-R2's second specimen made the apply path read a durable
    invalidation-obligation ledger BEFORE it writes, and an unreadable ledger
    refuses (that refusal is the fix). These cases predate the ledger and run
    without a database, where the real read classifies as ``unavailable``, so
    each gets an empty in-memory store. The ledger's own behaviour — open,
    carried, discharged, unreadable — is proved in
    ``test_kalshi_fabricated_loss_p062.py``, against a store that survives
    across calls.
    """
    from tests.test_kalshi_fabricated_loss_p062 import _DurableStore

    _DurableStore().install(monkeypatch)


def _venue_specimens() -> dict:
    return json.loads(
        (FIXTURES / "kalshi_fabricated_loss_specimens_p056.json").read_text()
    )


def _stored_legs() -> dict:
    return json.loads(
        (FIXTURES / "kalshi_fabricated_loss_stored_legs_p058.json").read_text()
    )


def _rows(payload):
    return [SimpleNamespace(**row) for row in payload]


# =============================================================================
# FINDING 1 — the mutating OFFSET
# =============================================================================


class TestFindingOneCursorCannotSkip:
    """A repair that deletes from its own population cannot be paged by count.

    The model is C-CERT-1852's own: a 100-row population, a 40-row window, and a
    page whose successful repairs remove its rows from the predicate. Under the
    shipped OFFSET the second page started at row 81 and reported ``exhausted``
    with rows 41-80 never examined. Under a keyset it cannot.
    """

    POPULATION = 100
    WINDOW = 40

    @staticmethod
    def _page(remaining, window):
        """One page of the SHIPPING predicate shape: ordered, windowed, keyset."""
        return sorted(remaining)[:window]

    def test_offset_paging_skips_a_whole_page_the_regression_this_replaces(self):
        """The defect, reproduced. Kept as a test so the fix has a control."""
        remaining = set(range(1, self.POPULATION + 1))
        seen: set[int] = set()
        offset = 0
        for _ in range(10):
            page = sorted(remaining)[offset : offset + self.WINDOW]
            if not page:
                break
            seen.update(page)
            remaining -= set(page)  # every row on the page was repaired
            offset += len(page)
        missed = set(range(1, self.POPULATION + 1)) - seen
        assert missed, "the offset model must still demonstrate the skip"
        assert len(missed) == 40
        assert min(missed) == 41 and max(missed) == 80

    def test_keyset_paging_misses_nothing_across_three_pages(self):
        remaining = set(range(1, self.POPULATION + 1))
        seen: set[int] = set()
        after = None
        pages = 0
        while True:
            candidates = [i for i in sorted(remaining) if after is None or i > after]
            page = candidates[: self.WINDOW]
            if not page:
                break
            pages += 1
            seen.update(page)
            remaining -= set(page)
            after = page[-1]
            assert not cursor_skips_unprocessed(
                selected_ids=page, processed_ids=page, next_after_id=after
            )
        assert pages > 1, "the fixture must repair more than one page"
        assert seen == set(range(1, self.POPULATION + 1))
        assert not remaining

    def test_a_partial_page_resumes_inside_itself_not_past_itself(self):
        """The wall-clock stop is the same bug one level down if the cursor is
        the last row RETURNED rather than the last row EXAMINED."""
        rows = _rows(
            [
                {"market_id": i, "resolution_date": None}
                for i in (10, 11, 12, 13, 14)
            ]
        )
        cursor = keyset_after(rows, examined=2)
        assert cursor["after_id"] == 11
        assert cursor_skips_unprocessed(
            selected_ids=[r.market_id for r in rows],
            processed_ids=[10, 11],
            next_after_id=14,
        ), "advancing to the last RETURNED row would skip 12 and 13"
        assert not cursor_skips_unprocessed(
            selected_ids=[r.market_id for r in rows],
            processed_ids=[10, 11],
            next_after_id=cursor["after_id"],
        )

    def test_nothing_examined_advances_nothing(self):
        assert keyset_after(_rows([{"market_id": 5, "resolution_date": None}]), 0) is None
        assert keyset_after([], 3) is None

    def test_the_work_sql_has_no_offset_and_carries_the_keyset(self):
        assert "OFFSET" not in rail._WORK_SQL.upper()
        assert "(fm.resolution_date, fm.id)" in rail._WORK_SQL
        # asyncpg drops a bind param followed by a `::` cast — CAST(...) form only.
        assert "CAST(:after_date AS timestamptz)" in rail._WORK_SQL
        assert ":after_date::" not in rail._WORK_SQL

    @pytest.mark.asyncio
    async def test_the_retired_offset_param_is_refused_by_name(self):
        out = await rail.repair(object(), apply=False, offset=40)
        assert out["refused"] == "OFFSET_CURSOR_RETIRED"
        assert out["measured"] is False

    def test_the_canonical_corpus_specimen_scores_against_this_rail(self):
        """``repair-cap-cursor-skip`` from the committed contract, run against
        the rail's OWN telemetry rather than against a model of it."""
        assert evaluate_repair_contract(
            candidate_ids=[10, 11, 12],
            processed_ids=[10],
            approved_ids=[10, 11, 12],
            mutated_ids=[10],
            dry_run_ids=None,
            next_cursor=12,
        ) == {
            "action": "REFUSE",
            "allowed_mutations": [],
            "reason_codes": [REASON_CURSOR_SKIP],
        }


# =============================================================================
# FINDING 2 — apply bound to the reviewed dry-run
# =============================================================================


def _plan(*legs) -> ApplyPlan:
    return build_plan(legs)


LEG_A = PlannedLeg(1, 100, "retract_fabricated", False, REPAIRABLE_SOURCE, "T-A")
LEG_B = PlannedLeg(2, 100, "restore_winner", False, REPAIRABLE_SOURCE, "T-B")


class TestFindingTwoApplyIsBound:
    def test_the_address_is_content_addressed_and_order_independent(self):
        assert _plan(LEG_A, LEG_B).plan_hash == _plan(LEG_B, LEG_A).plan_hash

    @pytest.mark.parametrize(
        "mutated",
        [
            PlannedLeg(1, 100, "restore_winner", False, REPAIRABLE_SOURCE, "T-A"),
            PlannedLeg(1, 100, "retract_fabricated", True, REPAIRABLE_SOURCE, "T-A"),
            PlannedLeg(1, 100, "retract_fabricated", False, "clob_field_repair", "T-A"),
            PlannedLeg(3, 100, "retract_fabricated", False, REPAIRABLE_SOURCE, "T-A"),
        ],
    )
    def test_every_field_the_apply_acts_on_moves_the_address(self, mutated):
        assert _plan(mutated, LEG_B).plan_hash != _plan(LEG_A, LEG_B).plan_hash

    def test_describing_a_plan_does_not_re_address_it(self):
        a = build_plan([LEG_A], context={"note": "first read"})
        b = build_plan([LEG_A], context={"note": "second read", "sport": "golf"})
        assert a.plan_hash == b.plan_hash

    def test_an_edited_artifact_is_refused_not_trusted(self):
        payload = _plan(LEG_A, LEG_B).as_payload()
        payload["legs"][0]["expected_source"] = "clob_never_graded"
        plan, reason = decode_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_round_trip_survives(self):
        original = _plan(LEG_A, LEG_B)
        plan, reason = decode_plan(json.loads(json.dumps(original.as_payload())))
        assert reason == "ok"
        assert plan.plan_hash == original.plan_hash
        assert plan.leg_ids == original.leg_ids

    def test_apply_first_with_no_plan_at_all_is_refused(self):
        ok, reasons = bind_apply(None, decode_reason="ok", presented_hash=None)
        assert not ok and reasons == [REASON_PLAN_MISSING]

    def test_apply_with_no_hash_against_a_real_plan_is_refused(self):
        ok, reasons = bind_apply(_plan(LEG_A), presented_hash=None)
        assert not ok and reasons == [REASON_PLAN_HASH_MISMATCH]

    def test_reviewing_census_a_and_applying_census_b_is_refused(self):
        reviewed = _plan(LEG_A)
        stored = _plan(LEG_A, LEG_B)  # the dry-run moved under the operator
        ok, reasons = bind_apply(stored, presented_hash=reviewed.plan_hash)
        assert not ok and reasons == [REASON_PLAN_HASH_MISMATCH]

    def test_the_matching_plan_is_allowed(self):
        plan = _plan(LEG_A, LEG_B)
        ok, reasons = bind_apply(plan, presented_hash=plan.plan_hash)
        assert ok and reasons == []

    @pytest.mark.asyncio
    async def test_the_shipping_apply_path_refuses_when_no_artifact_exists(
        self, monkeypatch
    ):
        async def _no_plan():
            return None, "plan artifact unreadable: missing"

        monkeypatch.setattr(rail, "_load_plan", _no_plan)
        out = await rail.repair(object(), apply=True, plan_hash="deadbeef")
        assert out["success"] is False
        assert REASON_PLAN_MISSING in out["refused"]

    @pytest.mark.asyncio
    async def test_the_shipping_apply_path_refuses_a_stale_hash(self, monkeypatch):
        plan = _plan(LEG_A, LEG_B)

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)
        out = await rail.repair(object(), apply=True, plan_hash="not-the-hash")
        assert out["success"] is False
        assert REASON_PLAN_HASH_MISMATCH in out["refused"]
        assert out["artifact_plan_hash"] == plan.plan_hash

    def test_apply_re_derives_nothing(self):
        """The structural half of the finding: the apply path must not contain
        the population read, the venue call, or the classifier."""
        import inspect

        src = inspect.getsource(rail._apply_reviewed_plan)
        for forbidden in ("_WORK_SQL", "_fetch_venue", "plan_market_legs", "classify_"):
            assert forbidden not in src, forbidden

    def test_a_mutation_the_plan_never_named_is_caught(self):
        assert evaluate_repair_contract(
            candidate_ids=[20],
            processed_ids=[20],
            approved_ids=[20],
            mutated_ids=[21],
            dry_run_ids=None,
            next_cursor=None,
        )["reason_codes"] == [REASON_OUTSIDE_APPROVED]


# =============================================================================
# FINDING 3 — compare-and-set on BOTH write forms
# =============================================================================


class _FakeResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _CASSession:
    """A session that answers an UPDATE the way PostgreSQL would.

    It holds real rows and applies the statement's own WHERE semantics for the
    two shapes this rail emits, so a fix that dropped the guard would be
    reported as writing — which is exactly what must fail.
    """

    def __init__(self, rows):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.committed = False
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        if "SELECT COUNT(*)" in sql:
            retracted = sum(
                1 for r in self.rows.values() if r["resolution_source"] == RETRACTION_SOURCE
            )
            winners = sum(1 for r in self.rows.values() if r["is_winner"])
            return SimpleNamespace(
                one=lambda: SimpleNamespace(
                    retracted_now=retracted, winners_now=winners
                )
            )
        if "SELECT id, source FROM futures_markets" in sql:
            return SimpleNamespace(all=lambda: [])
        if "UPDATE futures_outcomes" not in sql:
            return _FakeResult(0)

        row = self.rows.get(params["id"])
        if row is None:
            return _FakeResult(0)
        # The guard, evaluated exactly as written.
        if row["is_winner"] != params["prior_winner"]:
            return _FakeResult(0)
        if row["resolution_source"] != params["prior_source"]:
            return _FakeResult(0)
        if "SET is_winner = true" in sql:
            row["is_winner"] = True
            row["resolution_source"] = REPAIRABLE_SOURCE
        else:
            row["resolution_source"] = params["retraction"]
        return _FakeResult(1)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


async def _invalidation_ok(session, market_ids):
    return {
        "status": "invalidated" if market_ids else "nothing_written",
        "banked_units_discarded": 7 if market_ids else 0,
    }


class TestFindingThreeCompareAndSet:
    LEGS = (
        PlannedLeg(1, 500, "restore_winner", False, REPAIRABLE_SOURCE, "T-1"),
        PlannedLeg(2, 500, "retract_fabricated", False, REPAIRABLE_SOURCE, "T-2"),
    )

    def _session(self, overrides=None):
        rows = [
            {"id": 1, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE},
            {"id": 2, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE},
        ]
        for row in rows:
            row.update((overrides or {}).get(row["id"], {}))
        return _CASSession(rows)

    async def _run(self, session, monkeypatch, legs=None):
        plan = build_plan(legs or self.LEGS)

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)
        monkeypatch.setattr(
            rail, "invalidate_calibration_generation", _invalidation_ok
        )
        return await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

    @pytest.mark.asyncio
    async def test_the_undisturbed_case_writes_both_forms(self, monkeypatch):
        session = self._session()
        out = await self._run(session, monkeypatch)
        assert out["legs_written"] == 2
        assert out["winners_restored"] == 1 and out["losses_retracted"] == 1
        assert session.rows[1]["is_winner"] is True
        assert session.rows[2]["resolution_source"] == RETRACTION_SOURCE
        assert out["concurrent_drift_count"] == 0
        assert session.committed is True

    @pytest.mark.asyncio
    async def test_a_concurrent_grader_on_the_RESTORE_leg_is_never_clobbered(
        self, monkeypatch
    ):
        """The exact finding: the restore carried only ``NOT is_winner``, so a
        grader that replaced api_settlement with a real result between plan and
        write would have been overwritten by a stale api_settlement."""
        session = self._session({1: {"resolution_source": "clob_field_repair"}})
        out = await self._run(session, monkeypatch)
        assert session.rows[1]["resolution_source"] == "clob_field_repair"
        assert session.rows[1]["is_winner"] is False
        assert out["winners_restored"] == 0
        assert out["concurrent_drift_count"] == 1
        drift = out["concurrent_drift"][0]
        assert drift["leg_id"] == 1 and drift["reason"] == REASON_CONCURRENT_DRIFT
        assert drift["rows_affected"] == 0
        # and the sibling still applied — one moved row is not a batch abort
        assert session.rows[2]["resolution_source"] == RETRACTION_SOURCE

    @pytest.mark.asyncio
    async def test_a_leg_that_became_a_winner_under_the_plan_is_skipped(
        self, monkeypatch
    ):
        session = self._session({2: {"is_winner": True}})
        out = await self._run(session, monkeypatch)
        assert session.rows[2]["resolution_source"] == REPAIRABLE_SOURCE
        assert out["losses_retracted"] == 0
        assert out["concurrent_drift_count"] == 1

    @pytest.mark.asyncio
    async def test_both_write_statements_carry_the_prior_state(self, monkeypatch):
        session = self._session()
        await self._run(session, monkeypatch)
        updates = [s for s in session.statements if "UPDATE futures_outcomes" in s]
        assert len(updates) == 2
        for sql in updates:
            assert "is_winner = :prior_winner" in sql
            assert "resolution_source IS NOT DISTINCT FROM :prior_source" in sql

    @pytest.mark.asyncio
    async def test_a_fully_drifted_plan_writes_nothing_and_never_commits(
        self, monkeypatch
    ):
        session = self._session(
            {
                1: {"resolution_source": "datagolf_settlement"},
                2: {"resolution_source": "datagolf_settlement"},
            }
        )
        out = await self._run(session, monkeypatch)
        assert out["legs_written"] == 0
        assert out["concurrent_drift_count"] == 2
        assert session.committed is False
        assert out["after_reread"] is None
        # Attempted, reported and skipped — NOT silently dropped.
        assert out["attempted_leg_ids_equal_plan"] is True

    @pytest.mark.asyncio
    async def test_every_planned_leg_is_attempted_even_when_it_drifts(
        self, monkeypatch
    ):
        session = self._session({1: {"resolution_source": "clob_field_repair"}})
        out = await self._run(session, monkeypatch)
        attempted = sorted(
            [d["leg_id"] for d in out["concurrent_drift"]]
        ) + [1, 2]
        assert out["attempted_leg_ids_equal_plan"] is True
        assert set(attempted) == {1, 2}


# =============================================================================
# FINDING 4 — the invalidation is executable, counted, and gates success
# =============================================================================


class TestFindingFourInvalidationIsExecutable:
    LEGS = (PlannedLeg(1, 500, "retract_fabricated", False, REPAIRABLE_SOURCE, "T-1"),)

    def _session(self):
        return _CASSession(
            [{"id": 1, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE}]
        )

    async def _run(self, monkeypatch, invalidation):
        plan = build_plan(self.LEGS)

        async def _load():
            return plan, "ok"

        calls: list[set] = []

        async def _inv(session, market_ids):
            calls.append(set(market_ids))
            return invalidation

        monkeypatch.setattr(rail, "_load_plan", _load)
        monkeypatch.setattr(rail, "invalidate_calibration_generation", _inv)
        out = await rail.repair(self._session(), apply=True, plan_hash=plan.plan_hash)
        return out, calls

    @pytest.mark.asyncio
    async def test_the_apply_invokes_it_for_the_markets_it_wrote(self, monkeypatch):
        out, calls = await self._run(
            monkeypatch, {"status": "invalidated", "banked_units_discarded": 12}
        )
        assert calls == [{500}], "the invalidation must be CALLED, with the ids"
        assert out["invalidated_units"] == 12
        assert out["calibration_invalidation"]["status"] == "invalidated"
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_a_failed_invalidation_forces_success_false(self, monkeypatch):
        out, _ = await self._run(
            monkeypatch, {"status": "failed", "banked_units_discarded": None}
        )
        assert out["legs_written"] == 1, "the rows ARE repaired"
        assert out["success"] is False, "and the run still refuses to claim success"

    @pytest.mark.asyncio
    async def test_a_not_run_invalidation_forces_success_false(self, monkeypatch):
        out, _ = await self._run(monkeypatch, {"status": "not_run"})
        assert out["success"] is False

    def test_the_invalidation_is_a_function_the_apply_path_calls(self):
        import inspect

        assert inspect.iscoroutinefunction(rail.invalidate_calibration_generation)
        src = inspect.getsource(rail._apply_reviewed_plan)
        assert "await invalidate_calibration_generation(" in src
        # the gate is an expression, so assert the term appears inside it
        success_expr = src.split('"success": ', 1)[1].split('"success_note"', 1)[0]
        assert "invalidation_ok" in success_expr

    @pytest.mark.asyncio
    async def test_it_reports_nothing_written_rather_than_inventing_a_zero(self):
        out = await rail.invalidate_calibration_generation(object(), set())
        assert out["status"] == "nothing_written"

    def test_it_states_why_it_is_wholesale_rather_than_per_unit(self):
        doc = " ".join((rail.invalidate_calibration_generation.__doc__ or "").split())
        assert "accumulator" in doc
        assert "10 s statement timeout" in doc


# =============================================================================
# FINDING 5 — the specimen replay crosses the production mapping boundary
# =============================================================================


class TestFindingFiveReplayThroughProductionMapping:
    """The committed replay classified each VENUE row directly, so a mapper that
    applied one venue leg to every stored leg passed every assertion. These
    tests enter through ``plan_market_legs`` — the function ``repair()`` calls —
    with stored legs that carry their own ids and tickers.
    """

    SPECIMENS = (
        ("KXUSLGAME-26JUL24BIRNEW", {"retract_fabricated": 3}),
        ("KXARGPREMDIVSPREAD-26JUL28BANCAS", {"confirmed_loss": 5}),
        ("KXRDDT-26JULDAU", {"restore_winner": 3, "confirmed_loss": 7, "not_at_venue": 1}),
        ("KXPGAR1LEAD-COPC26", {"confirmed_loss": 150, "retract_fabricated": 2}),
    )

    @pytest.mark.parametrize("ticker,expected", SPECIMENS)
    def test_the_shipping_mapper_reproduces_the_live_answer(self, ticker, expected):
        from collections import Counter

        judged = plan_market_legs(
            _rows(_stored_legs()[ticker]), _venue_specimens()[ticker]
        )
        assert dict(Counter(item["verdict"] for item in judged)) == expected

    def test_a_positional_mapper_fails_this_suite(self):
        """The mutation C-CERT-1852 named: join by position, not by ticker.

        Run against the RDDT specimen, whose venue answer is mixed, a mapper
        that hands every stored leg the FIRST venue record produces a different
        verdict census. If this assertion ever stops holding, the fixture has
        stopped being able to tell the two mappers apart and the replay has
        gone back to being decoration.
        """
        from collections import Counter

        ticker = "KXRDDT-26JULDAU"
        venue = _venue_specimens()[ticker]
        legs = _rows(_stored_legs()[ticker])

        honest = Counter(
            i["verdict"] for i in plan_market_legs(legs, venue)
        )
        from app.utils.kalshi_fabricated_loss import classify_leg

        positional = Counter(
            classify_leg(
                bool(leg.is_winner),
                leg.resolution_source,
                venue[0].get("status"),
                venue[0].get("result"),
                present_at_venue=True,
            )
            for leg in legs
        )
        assert honest != positional

    def test_the_ticker_join_is_exact_not_prefix(self):
        venue = [{"ticker": "KX-A", "status": "finalized", "result": "yes"}]
        leg = SimpleNamespace(
            id=1, external_id="KX-AB", is_winner=False,
            resolution_source=REPAIRABLE_SOURCE,
        )
        assert plan_market_legs([leg], venue)[0]["verdict"] == "not_at_venue"

    def test_a_leg_the_venue_has_no_ticker_for_is_never_written(self):
        judged = plan_market_legs(
            _rows(_stored_legs()["KXRDDT-26JULDAU"]),
            _venue_specimens()["KXRDDT-26JULDAU"],
        )
        absent = [i for i in judged if i["verdict"] == "not_at_venue"]
        assert len(absent) == 1
        assert absent[0]["external_id"] == "KXRDDT-26JULDAU-TICKER-WE-INVENTED"
        assert all(i["verdict"] not in WRITING_VERDICTS for i in absent)

    def test_the_mapper_carries_the_prior_state_the_apply_compares_on(self):
        judged = plan_market_legs(
            _rows(_stored_legs()["KXUSLGAME-26JUL24BIRNEW"]),
            _venue_specimens()["KXUSLGAME-26JUL24BIRNEW"],
        )
        for item in judged:
            assert item["prior_source"] == REPAIRABLE_SOURCE
            assert item["prior_is_winner"] is False
            assert isinstance(item["leg_id"], int)

    def test_the_task_holds_no_second_mapping(self):
        import inspect

        src = inspect.getsource(rail)
        assert "by_ticker" not in src, "the join must live in the pure module only"
        assert "plan_market_legs(" in src

    def test_map_venue_by_ticker_is_what_both_sides_use(self):
        venue = _venue_specimens()["KXUSLGAME-26JUL24BIRNEW"]
        assert set(map_venue_by_ticker(venue)) == {m["ticker"] for m in venue}
        assert map_venue_by_ticker(None) == {}

    @pytest.mark.asyncio
    async def test_the_venue_fetch_follows_the_cursor_across_pages(self):
        """The paging half of finding 5 — the fixture now crosses a page
        boundary through the SHIPPING ``_fetch_venue``, whose cursor loop no
        test had ever executed."""
        venue = _venue_specimens()["KXPGAR1LEAD-COPC26"]
        pages = [(venue[:100], "cursor-1"), (venue[100:], None)]
        calls: list[dict] = []

        class _Service:
            async def get_markets(self, **kwargs):
                calls.append(kwargs)
                return pages[len(calls) - 1]

        collected, note = await rail._fetch_venue(_Service(), "KXPGAR1LEAD-COPC26")
        assert note == "ok"
        assert len(collected) == len(venue)
        assert len(calls) == 2
        assert calls[0]["cursor"] is None and calls[1]["cursor"] == "cursor-1"
        assert calls[0]["event_ticker"] == "KXPGAR1LEAD-COPC26"
        # and the mapper still resolves every leg after paging
        judged = plan_market_legs(
            _rows(_stored_legs()["KXPGAR1LEAD-COPC26"]), collected
        )
        assert not [i for i in judged if i["verdict"] == "not_at_venue"]

    @pytest.mark.asyncio
    async def test_a_transport_failure_is_unknown_never_an_empty_venue(self):
        class _Broken:
            async def get_markets(self, **kwargs):
                raise RuntimeError("boom")

        collected, note = await rail._fetch_venue(_Broken(), "KX-X")
        assert collected is None
        assert note.startswith("lookup_failed")


# =============================================================================
# The dispatcher must actually carry the new gate
# =============================================================================


class TestDispatcherCarriesTheGate:
    def test_plan_hash_and_the_keyset_reach_the_repair(self):
        import inspect

        from app.routes import admin_repairs

        params = inspect.signature(admin_repairs.run_repair).parameters
        for name in ("plan_hash", "after_id", "after_date"):
            assert name in params, name
        src = inspect.getsource(admin_repairs.run_repair)
        for name in ("plan_hash", "after_id", "after_date"):
            assert f'("{name}", {name})' in src

    def test_the_repair_signature_declares_them(self):
        import inspect

        params = inspect.signature(rail.repair).parameters
        for name in ("plan_hash", "after_id", "after_date"):
            assert name in params, name
