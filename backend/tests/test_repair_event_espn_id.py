"""The `events.espn_id` correction rail — #1947 population 1, SPEC-Q370.

Every named refusal state in the spec is reachable here, because the spec's own
rule is that a refusal collapsing two causes into one word sends the operator at
the wrong next action. A refusal code nothing can produce is a code that will be
wrong the first time it fires.

The population is the reason this matters rather than a style point. Between
review (2026-08-18) and this rail being written (2026-08-19), the five reviewed
rows produced FOUR different gate outcomes on their own, with nobody touching
them — four self-repaired and one drifted its commence_time. A gate that
answered "drift" to all five would have sent an operator to re-derive a plan
whose work was already done.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.tasks import repair_event_espn_id as rail
from app.utils.repair_apply_plan import (
    ESPN_ID_PLAN_SCHEMA,
    REASON_COMMENCE_DRIFTED,
    REASON_ESPN_ID_ALREADY_CORRECT,
    REASON_ESPN_ID_MOVED,
    REASON_EVENT_ROW_ABSENT,
    REASON_PLAN_CORRUPT,
    REASON_TRUE_ID_ALREADY_HELD,
    PlannedEspnIdCorrection,
    build_espn_id_correction_plan,
    decode_espn_id_correction_plan,
    espn_id_correction_gate,
    stillness_verdict,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
REVIEWED = REPO / "backend/app/data/event_espn_id_reviewed_pop1.json"


def _row(event_id=1, wrong="100", true="200", commence="2026-08-18T22:40:00Z"):
    return PlannedEspnIdCorrection(
        event_id=event_id,
        wrong_espn_id=wrong,
        true_espn_id=true,
        our_commence_time=commence,
        matchup="A @ B",
    )


# ---------------------------------------------------------------------------
# The reviewed set — the object a human approved
# ---------------------------------------------------------------------------


class TestTheReviewedSet:
    def test_it_is_committed_and_holds_the_five_reviewed_triples(self):
        """A reviewed set the deployed rail cannot open is not a reviewed set.

        It lives in `app/data/` rather than `.claude/handoff/` because the latter
        is gitignored — the artifact it was extracted from ships nowhere.
        """
        data = json.loads(REVIEWED.read_text())
        assert len(data["rows"]) == 5
        assert {r["event_id"] for r in data["rows"]} == {
            15199901, 15199886, 15199882, 15200229, 15200216
        }

    def test_every_reviewed_row_carries_all_four_addressed_fields(self):
        """A field the digest addresses must not be able to decode as None."""
        for row in json.loads(REVIEWED.read_text())["rows"]:
            for key in ("event_id", "wrong_espn_id", "true_espn_id", "our_commence_time"):
                assert row.get(key) not in (None, ""), f"{row.get('event_id')}: {key}"

    def test_no_reviewed_row_is_self_pointing(self):
        """A no-op WRITE reports rowcount 1 — APPLIED, while nothing changed."""
        for row in json.loads(REVIEWED.read_text())["rows"]:
            assert row["wrong_espn_id"] != row["true_espn_id"]

    def test_the_registry_refuses_an_unknown_population_by_name(self):
        assert rail._reviewed_set_path("nope") is None
        assert rail._load_reviewed_set("nope")[1] == rail.REASON_UNKNOWN_POPULATION

    def test_rows_from_reviewed_round_trips_the_committed_file(self):
        rows = rail.rows_from_reviewed(json.loads(REVIEWED.read_text()))
        assert len(rows) == 5
        assert all(isinstance(r.event_id, int) for r in rows)
        assert all(isinstance(r.wrong_espn_id, str) for r in rows)


# ---------------------------------------------------------------------------
# The address
# ---------------------------------------------------------------------------


class TestThePlanHashAddressesWhatTheReviewerRead:
    def test_commence_time_is_inside_the_address(self):
        """Queue 368's `sport_id` finding, one rail over.

        `commence_time` is how a reviewer knows WHICH GAME a row is, and #1947's
        entire history is rows whose commence_time moved. Outside the digest, an
        artifact could be edited to a different game while keeping its approved
        address and decoding clean.
        """
        a = build_espn_id_correction_plan([_row(commence="2026-08-18T22:40:00Z")])
        b = build_espn_id_correction_plan([_row(commence="2026-08-19T22:40:00Z")])
        assert a.plan_hash != b.plan_hash

    def test_matchup_is_outside_the_address(self):
        """Prose assembled for the reviewer. Re-wording must not re-address."""
        a = build_espn_id_correction_plan([_row()])
        b = build_espn_id_correction_plan(
            [PlannedEspnIdCorrection(1, "100", "200", "2026-08-18T22:40:00Z", "reworded")]
        )
        assert a.plan_hash == b.plan_hash

    @pytest.mark.parametrize(
        "kwargs", [{"event_id": 2}, {"wrong": "101"}, {"true": "201"}]
    )
    def test_every_written_or_compared_field_re_addresses(self, kwargs):
        base = build_espn_id_correction_plan([_row()])
        assert build_espn_id_correction_plan([_row(**kwargs)]).plan_hash != base.plan_hash

    def test_the_namespace_cannot_collide_with_a_sibling_rail(self):
        """Two plans holding the same integers must never share an address."""
        from app.utils.repair_apply_plan import (
            PlannedMappingRepair,
            build_mapping_repair_plan,
        )

        ours = build_espn_id_correction_plan([_row()])
        theirs = build_mapping_repair_plan(
            [PlannedMappingRepair(1, "espn", "baseball_mlb", "x", 100, "A", 200, "B")]
        )
        assert ours.plan_hash != theirs.plan_hash

    def test_row_order_does_not_change_the_address(self):
        rows = [_row(event_id=1), _row(event_id=2)]
        assert (
            build_espn_id_correction_plan(rows).plan_hash
            == build_espn_id_correction_plan(list(reversed(rows))).plan_hash
        )


class TestDecodeRefusesRatherThanRepairs:
    def test_a_good_payload_round_trips(self):
        plan = build_espn_id_correction_plan([_row(), _row(event_id=2, true="201")])
        decoded, reason = decode_espn_id_correction_plan(plan.as_payload())
        assert reason == "ok"
        assert decoded.plan_hash == plan.plan_hash

    def test_an_edited_row_no_longer_matches_its_stored_address(self):
        payload = build_espn_id_correction_plan([_row()]).as_payload()
        payload["rows"][0]["true_espn_id"] = "999"
        assert decode_espn_id_correction_plan(payload) == (None, REASON_PLAN_CORRUPT)

    def test_an_edited_commence_time_no_longer_matches_either(self):
        payload = build_espn_id_correction_plan([_row()]).as_payload()
        payload["rows"][0]["our_commence_time"] = "2030-01-01T00:00:00Z"
        assert decode_espn_id_correction_plan(payload) == (None, REASON_PLAN_CORRUPT)

    def test_a_missing_field_is_corrupt_not_a_None_that_sails_past(self):
        payload = build_espn_id_correction_plan([_row()]).as_payload()
        del payload["rows"][0]["wrong_espn_id"]
        assert decode_espn_id_correction_plan(payload) == (None, REASON_PLAN_CORRUPT)

    def test_another_rails_schema_is_refused(self):
        payload = build_espn_id_correction_plan([_row()]).as_payload()
        payload["schema"] = "event-create-from-truth-plan/v3"
        assert decode_espn_id_correction_plan(payload) == (None, REASON_PLAN_CORRUPT)

    def test_a_duplicate_event_id_is_refused(self):
        """Two rows for one event: whichever ran second would silently win."""
        plan = build_espn_id_correction_plan([_row(), _row(true="201")])
        assert plan.duplicate_event_ids() == [1]
        assert decode_espn_id_correction_plan(plan.as_payload()) == (None, REASON_PLAN_CORRUPT)

    def test_a_self_pointing_row_is_refused(self):
        plan = build_espn_id_correction_plan([_row(wrong="100", true="100")])
        assert plan.self_pointing_rows() == [1]
        assert decode_espn_id_correction_plan(plan.as_payload()) == (None, REASON_PLAN_CORRUPT)

    def test_two_events_assigned_one_true_id_is_refused(self):
        """`ix_events_espn_id` is NOT unique, so the plan is the only place to catch it."""
        plan = build_espn_id_correction_plan(
            [_row(event_id=1, true="200"), _row(event_id=2, wrong="101", true="200")]
        )
        assert plan.colliding_true_ids() == ["200"]
        assert decode_espn_id_correction_plan(plan.as_payload()) == (None, REASON_PLAN_CORRUPT)

    def test_a_non_mapping_is_MISSING_not_CORRUPT(self):
        """MISSING sends an operator to make a plan; CORRUPT says investigate."""
        from app.utils.repair_apply_plan import REASON_PLAN_MISSING

        assert decode_espn_id_correction_plan(None) == (None, REASON_PLAN_MISSING)


# ---------------------------------------------------------------------------
# The gate — every named refusal reachable, siblings never cancelled
# ---------------------------------------------------------------------------


class TestTheGateNamesEachCauseSeparately:
    def test_a_matching_row_is_actionable(self):
        plan = build_espn_id_correction_plan([_row()])
        actionable, retired = espn_id_correction_gate(
            plan, {1: {"espn_id": "100", "commence_time": "2026-08-18T22:40:00Z"}}
        )
        assert [r.event_id for r in actionable] == [1]
        assert retired == []

    def test_already_correct_is_SUCCESS_not_drift(self):
        """The live specimen: 4 of the 5 reviewed rows reached this state alone.

        Reported as ALREADY_CORRECT rather than MOVED because "the ordinary
        pipeline got there first" means that row is DONE. Collapsing it into
        drift would send an operator to re-derive a plan with nothing left to do.
        """
        plan = build_espn_id_correction_plan([_row()])
        actionable, retired = espn_id_correction_gate(
            plan, {1: {"espn_id": "200", "commence_time": "2026-08-18T22:40:00Z"}}
        )
        assert actionable == []
        assert retired[0]["reason_code"] == REASON_ESPN_ID_ALREADY_CORRECT

    def test_a_third_id_is_MOVED(self):
        plan = build_espn_id_correction_plan([_row()])
        _, retired = espn_id_correction_gate(
            plan, {1: {"espn_id": "999", "commence_time": "2026-08-18T22:40:00Z"}}
        )
        assert retired[0]["reason_code"] == REASON_ESPN_ID_MOVED
        assert retired[0]["observed_espn_id"] == "999"

    def test_no_row_is_ABSENT(self):
        plan = build_espn_id_correction_plan([_row()])
        _, retired = espn_id_correction_gate(plan, {1: None})
        assert retired[0]["reason_code"] == REASON_EVENT_ROW_ABSENT

    def test_a_moved_commence_time_is_COMMENCE_DRIFTED(self):
        """The live specimen: 15200216 was reviewed at 2026-08-20T18:10Z and
        production now reads 2026-08-18 23:40 — it is not the game reviewed."""
        plan = build_espn_id_correction_plan([_row()])
        _, retired = espn_id_correction_gate(
            plan, {1: {"espn_id": "100", "commence_time": "2026-08-19 05:00:00+00:00"}}
        )
        assert retired[0]["reason_code"] == REASON_COMMENCE_DRIFTED
        assert retired[0]["observed_commence_time"] == "2026-08-19 05:00:00+00:00"

    def test_a_true_id_held_by_another_row_is_named_before_the_write(self):
        plan = build_espn_id_correction_plan([_row()])
        _, retired = espn_id_correction_gate(
            plan,
            {1: {"espn_id": "100", "commence_time": "2026-08-18T22:40:00Z"}},
            true_id_holders={"200": [77]},
        )
        assert retired[0]["reason_code"] == REASON_TRUE_ID_ALREADY_HELD
        assert retired[0]["held_by_event_ids"] == [77]

    def test_the_row_itself_holding_the_true_id_is_not_a_collision(self):
        """A row that self-healed holds its own true id. That is ALREADY_CORRECT,
        not a collision with itself."""
        plan = build_espn_id_correction_plan([_row()])
        _, retired = espn_id_correction_gate(
            plan,
            {1: {"espn_id": "200", "commence_time": "2026-08-18T22:40:00Z"}},
            true_id_holders={"200": [1]},
        )
        assert retired[0]["reason_code"] == REASON_ESPN_ID_ALREADY_CORRECT

    def test_ONE_retirement_never_cancels_its_siblings(self):
        """The count-vs-set rule on the failure path.

        A wholesale refusal would let one upstream repair cancel every approved
        sibling — the failure `create_gate`'s docstring records from the other rail.
        """
        plan = build_espn_id_correction_plan(
            [_row(event_id=1), _row(event_id=2, wrong="101", true="201")]
        )
        actionable, retired = espn_id_correction_gate(
            plan,
            {
                1: {"espn_id": "200", "commence_time": "2026-08-18T22:40:00Z"},
                2: {"espn_id": "101", "commence_time": "2026-08-18T22:40:00Z"},
            },
        )
        assert [r.event_id for r in actionable] == [2]
        assert len(retired) == 1

    @pytest.mark.parametrize(
        "spelling",
        [
            "2026-08-18 22:40:00+00:00",  # what PostgreSQL hands back
            "2026-08-18T22:40:00+00:00",
            "2026-08-18T22:40:00Z",
        ],
    )
    def test_a_different_SPELLING_of_the_same_instant_is_not_drift(self, spelling):
        """Otherwise the gate retires every row and looks exactly like one that
        works — right up until someone notices it has never written anything."""
        plan = build_espn_id_correction_plan([_row(commence="2026-08-18T22:40:00Z")])
        actionable, retired = espn_id_correction_gate(
            plan, {1: {"espn_id": "100", "commence_time": spelling}}
        )
        assert [r.event_id for r in actionable] == [1], retired

    def test_a_different_INSTANT_still_drifts(self):
        """The normalizer normalizes spelling, never value."""
        plan = build_espn_id_correction_plan([_row(commence="2026-08-18T22:40:00Z")])
        _, retired = espn_id_correction_gate(
            plan, {1: {"espn_id": "100", "commence_time": "2026-08-18 22:41:00+00:00"}}
        )
        assert retired[0]["reason_code"] == REASON_COMMENCE_DRIFTED

    def test_an_unparseable_commence_time_drifts_loudly_rather_than_matching(self):
        plan = build_espn_id_correction_plan([_row()])
        _, retired = espn_id_correction_gate(
            plan, {1: {"espn_id": "100", "commence_time": "not a timestamp"}}
        )
        assert retired[0]["reason_code"] == REASON_COMMENCE_DRIFTED


# ---------------------------------------------------------------------------
# Ruling 095 — stillness is a precondition
# ---------------------------------------------------------------------------


def _probe(at, espn_id="100", commence="2026-08-18T22:40:00Z"):
    return {"at": at, "rows": {"1": {"espn_id": espn_id, "commence_time": commence}}}


class TestStillnessIsProvenNotAssumed:
    def test_three_reads_over_five_minutes_with_no_movement_is_still(self):
        still, detail = stillness_verdict([_probe(0), _probe(200), _probe(400)])
        assert still, detail
        assert detail["moved_event_ids"] == []

    def test_two_reads_is_not_enough_however_wide_the_span(self):
        still, detail = stillness_verdict([_probe(0), _probe(100_000)])
        assert not still
        assert detail["reads"] == 2

    def test_three_reads_inside_the_span_is_not_enough(self):
        """The flap this guards is a ~2-minute cycle. Three reads a second apart
        would all land inside one phase of it and agree perfectly."""
        still, _ = stillness_verdict([_probe(0), _probe(1), _probe(2)])
        assert not still

    def test_a_row_that_MOVED_defeats_stillness_and_is_named(self):
        still, detail = stillness_verdict(
            [_probe(0), _probe(200), _probe(400, espn_id="999")]
        )
        assert not still
        assert detail["moved_event_ids"] == [1]

    def test_a_commence_time_move_alone_defeats_stillness(self):
        """15199901 moved commence sixteen hours while keeping its id."""
        still, detail = stillness_verdict(
            [_probe(0), _probe(200), _probe(400, commence="2026-08-19T16:35:00Z")]
        )
        assert not still
        assert detail["moved_event_ids"] == [1]

    def test_a_refusal_says_WHICH_condition_failed(self):
        _, detail = stillness_verdict([_probe(0)])
        assert {"reads", "span_s", "moved_event_ids", "reason_code"} <= set(detail)

    def test_no_probes_is_not_still(self):
        still, _ = stillness_verdict([])
        assert not still

    def test_spelling_differences_across_probes_are_not_movement(self):
        still, detail = stillness_verdict(
            [
                _probe(0, commence="2026-08-18T22:40:00Z"),
                _probe(200, commence="2026-08-18 22:40:00+00:00"),
                _probe(400, commence="2026-08-18T22:40:00+00:00"),
            ]
        )
        assert still, detail


# ---------------------------------------------------------------------------
# The rail's structural promises, asserted on the source
# ---------------------------------------------------------------------------


class TestTheRailCannotQuietlyBecomeSomethingElse:
    SRC = pathlib.Path(rail.__file__).read_text()

    def test_the_compare_is_inside_the_UPDATE(self):
        """A check in FRONT of the statement reads a world the write then changes."""
        import re

        assert re.search(
            r"UPDATE\s+events\s+SET\s+espn_id\s*=\s*:true_espn_id\s+"
            r"WHERE\s+id\s*=\s*:event_id\s+AND\s+espn_id\s*=\s*:wrong_espn_id",
            self.SRC,
        ), "the compare must be the WHERE clause of the writing statement"

    #: The module's compiled SQL, which is the only thing that reaches the
    #: database. Asserting against the whole source file would grade the
    #: DOCSTRINGS — and the docstrings quote both an `UPDATE … SET` sketch and
    #: the sentence "No branch of this rail deletes a row", so a naive substring
    #: check on the source fails on the prose that explains the invariant. That
    #: is the measuring-the-labeller shape (ruling 042) in a guard test.
    SQL = " ".join(
        str(getattr(rail, name))
        for name in dir(rail)
        if name.endswith("_SQL")
    ).upper()

    def test_it_writes_exactly_one_column(self):
        """Ruling (a) withdrew status/score/completed_at; #1981's writer owns them."""
        import re

        sets = sorted(set(re.findall(r"SET\s+(\w+)\s*=", self.SQL)))
        assert sets == ["ESPN_ID"], sets

    def test_no_branch_deletes_a_row(self):
        """Correction, never deletion (ruling 079)."""
        assert "DELETE" not in self.SQL
        assert "TRUNCATE" not in self.SQL

    def test_the_sql_constants_are_the_only_statements_the_rail_runs(self):
        """The guard above is only worth anything if no statement bypasses it.

        Every `session.execute` must be handed one of the module-level `_*_SQL`
        constants. An inline `text("…")` at a call site would be invisible to the
        one-column and no-delete assertions above — a guard with a documented
        hole is not a guard, it is a claim.
        """
        import re

        executed = re.findall(r"session\.execute\(\s*([A-Za-z_][\w.]*)", self.SRC)
        assert executed, "no session.execute call found — did the rail move?"
        assert all(name.endswith("_SQL") for name in executed), executed

    def test_it_locks_the_row_before_reading_it(self):
        assert "FOR UPDATE" in self.SRC

    def test_the_apply_path_does_not_call_the_deriver(self):
        """The plan IS the work list. A work list that can be recomputed at apply
        time can differ from the reviewed one, and no after-measurement can say
        afterwards which of the two you wrote."""
        start = self.SRC.index("async def _apply_reviewed_plan")
        end = self.SRC.index("# Entry point")
        body = self.SRC[start:end]
        assert "_load_reviewed_set" not in body
        assert "rows_from_reviewed" not in body
        assert "build_espn_id_correction_plan" not in body

    def test_the_deriver_stamps_no_approval_it_cannot_cite(self):
        """Ruling 092. A forged credential is worse than none: a missing one
        prompts the question, a forged one answers it."""
        import re

        assert not re.search(r'"ruling"\s*:', self.SRC)
        assert not re.search(r'"approved_by"\s*:', self.SRC)

    def test_it_imports_the_primitives_rather_than_re_implementing_them(self):
        assert "from app.utils.repair_apply_plan import" in self.SRC
        assert "def bind_apply" not in self.SRC
        assert "def digest_fields" not in self.SRC

    def test_the_advisory_lock_key_is_namespaced_against_the_sibling_rails(self):
        """This rail's lock for event N must not collide with the CREATE rail's
        lock for provider id N."""
        import zlib

        from app.tasks.create_events_from_truth import _lock_key as create_key

        assert rail._lock_key(12345) != create_key("12345")
        assert rail._lock_key(12345) == (
            zlib.crc32(b"espn_id:12345") & 0x7FFFFFFF
        )

    def test_it_commits_per_row(self):
        """`events` is hot — one long transaction over the set contends with ingest."""
        assert "await session.commit()" in self.SRC

    def test_it_verifies_after_writing_by_re_reading(self):
        """A rail that reports only what it INTENDED is the claim-not-execution
        class — the shape that produced `miswired_after=0` on the binding rail."""
        assert "after_verification" in self.SRC
        assert "still_holding_wrong_id" in self.SRC
        assert "true_espn_ids_held_by_more_than_one_row" in self.SRC

    def test_the_schema_is_this_rails_own(self):
        assert ESPN_ID_PLAN_SCHEMA == "event-espn-id-correction-plan/v1"


class TestTheRailHasAnAddressSomebodyCanCall:
    """The gap this whole rail exists to close was *an apply path that did not
    exist*. Building one and not registering it repeats the finding one layer up:
    a rail nobody can invoke is a plan object with extra steps.
    """

    def test_it_is_registered_in_the_repair_dispatcher(self):
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["event-espn-id"] == (
            "app.tasks.repair_event_espn_id", "repair"
        )

    def test_the_dispatcher_passes_through_every_param_the_rail_declares(self):
        """A declared param the dispatcher drops is dead over HTTP — the exact
        defect queue 374 found on `since`, which was in the signature and not in
        the passthrough tuple, so the bound could never be supplied."""
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

    def test_the_dispatcher_declares_those_params_as_query_args(self):
        """In the tuple but not in the signature is the same hole, mirrored."""
        import inspect

        from app.routes import admin_repairs

        query_params = set(inspect.signature(admin_repairs.run_repair).parameters)
        for name in ("population", "plan_hash", "probe"):
            assert name in query_params, name
