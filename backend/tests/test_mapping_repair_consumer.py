"""#1918 queue 373 — the attended MAPPING consumer and its address.

`C-APPLY-PRE-MAPPING` blocked on two build gaps, both of which this file guards:

1. **No consumer.** The rows were certified clean and the plan was staged, but
   every ``decode_mapping_repair_plan`` call site was going to be the definition
   module, the deriver, or a test. A certification cannot certify an apply path
   that does not exist.
2. **A forgeable address.** ``derive_mapping_repair_plan.py`` addressed the plan
   with a raw ``"|".join`` over eight fields, four of them free text. That is not
   injective, so two materially different reviewed rows could share one content
   address — and the address is the only thing carrying Alex's approval forward.
"""

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.calibration_phase_ledger import input_fingerprint
from app.utils.repair_apply_plan import (
    MAPPING_REPAIR_PLAN_SCHEMA,
    REASON_MAPPING_BEFORE_DRIFT,
    REASON_MAPPING_ROW_MISSING,
    REASON_OUTSIDE_APPROVED,
    REASON_PLAN_CORRUPT,
    REASON_PLAN_HASH_MISMATCH,
    MappingRepairPlan,
    PlannedMappingRepair,
    build_mapping_repair_plan,
    decode_mapping_repair_plan,
    digest_fields,
    mapping_repair_gate,
)

_NS = "team-identity-mapping-repair-plan"

# The COMMITTED reviewed set — deliberately NOT `.claude/handoff/`, which is
# gitignored and therefore absent in CI and on Heroku. A fixture that skipped
# when the artifact was missing would have let the whole membership proof pass
# vacuously on every machine but the one that staged it.
STAGED = (
    pathlib.Path(__file__).resolve().parents[1]
    / "app/data/mapping_repair_reviewed_130.json"
)


def _row(**kw) -> PlannedMappingRepair:
    base = dict(
        mapping_id=1164132,
        source="polymarket",
        sport_key="baseball_mlb_preseason",
        source_name="San Diego Padres",
        before_team_id=851,
        before_club="Chicago White Sox",
        after_team_id=867,
        after_club="San Diego Padres",
    )
    base.update(kw)
    return PlannedMappingRepair(**base)


def _old_join(r: PlannedMappingRepair) -> str:
    """The pre-fix encoding, reproduced so the collision can be SHOWN, not asserted."""
    return "|".join(
        [
            str(r.mapping_id), r.source, r.sport_key, r.source_name,
            str(r.before_team_id), r.before_club,
            str(r.after_team_id), r.after_club,
        ]
    )


# ---------------------------------------------------------------------------
# The address
# ---------------------------------------------------------------------------


class TestAddressIsNotForgeable:
    """The cert's hostile pair, and the general property behind it."""

    def test_the_certs_hostile_pair_collided_under_the_old_encoder(self):
        """Shown, not assumed — a fix whose defect was never demonstrated is a guess."""
        a = _row(source="poly|market", sport_key="baseball_mlb")
        b = _row(source="poly", sport_key="market|baseball_mlb")
        assert _old_join(a) == _old_join(b) == (
            "1164132|poly|market|baseball_mlb|San Diego Padres|851|"
            "Chicago White Sox|867|San Diego Padres"
        )

    def test_the_certs_hostile_pair_produces_different_addresses(self):
        """THE verify named in the C-APPLY-PRE-MAPPING addendum."""
        a = _row(source="poly|market", sport_key="baseball_mlb")
        b = _row(source="poly", sport_key="market|baseball_mlb")

        assert a.digest_line() != b.digest_line()

        addr_a = build_mapping_repair_plan([a]).plan_hash
        addr_b = build_mapping_repair_plan([b]).plan_hash
        assert addr_a != addr_b, (
            "two materially different reviewed rows share one content address — "
            "the address cannot carry an approval"
        )

    @pytest.mark.parametrize(
        "field,left,right",
        [
            ("source", "a|b", "a"),
            ("sport_key", "x|y", "x"),
            ("source_name", "Real Madrid|B", "Real Madrid"),
            ("before_club", "Old|Club", "Old"),
            ("after_club", "New|Club", "New"),
        ],
    )
    def test_every_free_text_field_is_boundary_safe(self, field, left, right):
        """A pipe in ANY text field must not be able to imitate a boundary."""
        a = build_mapping_repair_plan([_row(**{field: left})]).plan_hash
        b = build_mapping_repair_plan([_row(**{field: right})]).plan_hash
        assert a != b

    def test_length_prefix_encoding_is_what_separates_them(self):
        assert digest_fields("Old|Club", "New") != digest_fields("Old", "Club|New")
        assert digest_fields("Old|Club", "New") == "8:Old|Club|3:New"


class TestStagedOneThirtyMembership:
    """The approval carries only if the ROWS are the same rows."""

    @pytest.fixture
    def staged(self):
        # NOT skipped when absent. A missing reviewed set is a failure — the rail
        # cannot run without it, and a skip here would hide exactly that.
        assert STAGED.exists(), f"reviewed set missing: {STAGED}"
        return json.loads(STAGED.read_text())

    def test_the_reviewed_set_is_committed_and_not_in_a_gitignored_dir(self):
        """The rail reads this file on Heroku. `.claude/` is gitignored."""
        import app.tasks.repair_team_identity_mapping as rm

        assert rm.STAGED_ARTIFACT == "app/data/mapping_repair_reviewed_130.json"
        assert not rm.STAGED_ARTIFACT.startswith(".claude")
        assert rm._staged_path().exists(), (
            f"the consumer resolves its reviewed set to {rm._staged_path()}, "
            f"which does not exist"
        )

    @pytest.fixture
    def plan(self, staged) -> MappingRepairPlan:
        return build_mapping_repair_plan(
            PlannedMappingRepair(
                mapping_id=int(r["mapping_id"]),
                source=r["source"],
                sport_key=r["sport_key"],
                source_name=r["source_name"],
                before_team_id=int(r["before"]["team_id"]),
                before_club=r["before"]["club"],
                after_team_id=int(r["after"]["team_id"]),
                after_club=r["after"]["club"],
            )
            for r in staged["rows"]
        )

    def test_the_staged_v1_address_is_reproducible(self, staged):
        """Proves the OLD encoding is faithfully reproduced here.

        Without this the claim "only the encoder changed" is unfalsifiable — a
        different v2 address could equally mean the rows moved.
        """
        lines = sorted(
            "|".join(
                [
                    str(r["mapping_id"]), r["source"], r["sport_key"], r["source_name"],
                    str(r["before"]["team_id"]), r["before"]["club"],
                    str(r["after"]["team_id"]), r["after"]["club"],
                ]
            )
            for r in staged["rows"]
        )
        assert input_fingerprint(_NS, str(len(lines)), *lines) == staged["v1_plan_hash"]
        assert staged["v1_plan_hash"] == "6b4a42f85a3cd169b611ac7105a7a1e8"

    def test_membership_is_byte_identical(self, staged, plan):
        """Same 130 rows, same eight fields each. Only the address moved."""
        as_tuples = lambda rows: sorted(  # noqa: E731
            (
                int(r["mapping_id"]), r["source"], r["sport_key"], r["source_name"],
                int(r["before"]["team_id"]), r["before"]["club"],
                int(r["after"]["team_id"]), r["after"]["club"],
            )
            for r in rows
        )
        assert as_tuples(staged["rows"]) == sorted(
            (
                p.mapping_id, p.source, p.sport_key, p.source_name,
                p.before_team_id, p.before_club, p.after_team_id, p.after_club,
            )
            for p in plan.rows
        )
        assert len(plan.rows) == 130

    def test_the_v2_address_is_stable(self, plan):
        """Pinned so an unnoticed encoder change cannot silently re-address it."""
        assert plan.plan_hash == "dd4de8942f41ee020a073a4147f64204"

    def test_the_reviewed_set_has_no_duplicates_and_no_no_ops(self, plan):
        assert plan.duplicate_mapping_ids() == []
        assert plan.self_pointing_rows() == []

    def test_the_four_held_out_rows_are_absent(self, plan):
        """The three the live rotation moves, plus the one never reviewed."""
        assert set(plan.mapping_ids).isdisjoint({4168917, 4168966, 4168971, 35192094})


class TestDecodeRefuses:
    def test_v1_schema_refuses_as_corrupt(self):
        payload = build_mapping_repair_plan([_row()]).as_payload()
        payload["schema"] = "team-identity-mapping-repair-plan/v1"
        plan, reason = decode_mapping_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_tampered_club_name_refuses(self):
        """The club names are what the human read; the address must notice."""
        payload = build_mapping_repair_plan([_row()]).as_payload()
        payload["rows"][0]["after"]["club"] = "Somebody Else"
        plan, reason = decode_mapping_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_tampered_team_id_refuses(self):
        payload = build_mapping_repair_plan([_row()]).as_payload()
        payload["rows"][0]["after"]["team_id"] = 999999
        plan, reason = decode_mapping_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_a_missing_field_refuses_rather_than_decoding_as_none(self):
        payload = build_mapping_repair_plan([_row()]).as_payload()
        del payload["rows"][0]["before"]["team_id"]
        plan, reason = decode_mapping_repair_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_duplicate_mapping_ids_refuse(self):
        plan = build_mapping_repair_plan([_row(), _row()])
        decoded, reason = decode_mapping_repair_plan(plan.as_payload())
        assert decoded is None and reason == REASON_PLAN_CORRUPT

    def test_a_self_pointing_row_refuses(self):
        """A no-op WRITE would report as applied while changing nothing."""
        plan = build_mapping_repair_plan([_row(after_team_id=851)])
        decoded, reason = decode_mapping_repair_plan(plan.as_payload())
        assert decoded is None and reason == REASON_PLAN_CORRUPT

    def test_a_clean_plan_round_trips(self):
        plan = build_mapping_repair_plan([_row()])
        decoded, reason = decode_mapping_repair_plan(plan.as_payload())
        assert reason == "ok" and decoded.plan_hash == plan.plan_hash


# ---------------------------------------------------------------------------
# The gate — before.team_id, as a SET, with per-row retirement
# ---------------------------------------------------------------------------


class TestMappingRepairGate:
    def test_all_rows_still_holding_before_passes(self):
        plan = build_mapping_repair_plan([_row(mapping_id=1), _row(mapping_id=2)])
        ok, drifted = mapping_repair_gate(plan, {1: 851, 2: 851})
        assert ok and drifted == []

    def test_a_rotated_row_is_named_not_skipped(self):
        plan = build_mapping_repair_plan([_row(mapping_id=1)])
        ok, drifted = mapping_repair_gate(plan, {1: 999})
        assert not ok
        assert drifted == [
            {
                "mapping_id": 1,
                "expected_before_team_id": 851,
                "observed_team_id": 999,
                "reason_code": REASON_MAPPING_BEFORE_DRIFT,
            }
        ]

    def test_a_vanished_row_is_a_different_named_reason(self):
        plan = build_mapping_repair_plan([_row(mapping_id=1)])
        ok, drifted = mapping_repair_gate(plan, {})
        assert not ok and drifted[0]["reason_code"] == REASON_MAPPING_ROW_MISSING

    def test_one_drifted_row_does_not_cancel_its_siblings(self):
        """The failure create_gate's docstring records, asserted on this rail.

        A wholesale refusal would let one live ``resolve_team`` re-registration
        cancel 129 approved repairs.
        """
        plan = build_mapping_repair_plan(
            [_row(mapping_id=i) for i in (1, 2, 3)]
        )
        ok, drifted = mapping_repair_gate(plan, {1: 851, 2: 999, 3: 851})
        assert not ok
        assert [d["mapping_id"] for d in drifted] == [2]


# ---------------------------------------------------------------------------
# The consumer
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return self._rows

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self._rows)


class TestConsumerRefusals:
    async def test_apply_without_a_plan_hash_refuses(self, monkeypatch):
        import app.tasks.repair_team_identity_mapping as rm

        plan = build_mapping_repair_plan([_row()])
        monkeypatch.setattr(rm, "_load_plan", AsyncMock(return_value=(plan, "ok")))
        out = await rm.repair(AsyncMock(), apply=True, plan_hash=None)
        assert out["applied"] is False
        assert out["reason_codes"] == [REASON_PLAN_HASH_MISMATCH]

    async def test_apply_with_the_wrong_plan_hash_refuses(self, monkeypatch):
        import app.tasks.repair_team_identity_mapping as rm

        plan = build_mapping_repair_plan([_row()])
        monkeypatch.setattr(rm, "_load_plan", AsyncMock(return_value=(plan, "ok")))
        out = await rm.repair(AsyncMock(), apply=True, plan_hash="deadbeef")
        assert out["applied"] is False
        assert out["reason_codes"] == [REASON_PLAN_HASH_MISMATCH]

    async def test_a_corrupt_artifact_is_not_reported_as_missing(self, monkeypatch):
        """Telling an operator MISSING sends them to regenerate — the one action
        that destroys the evidence (gotcha #53)."""
        import app.tasks.repair_team_identity_mapping as rm

        monkeypatch.setattr(
            rm, "_load_plan", AsyncMock(return_value=(None, REASON_PLAN_CORRUPT))
        )
        out = await rm.repair(AsyncMock(), apply=True, plan_hash="whatever")
        assert out["reason_codes"] == [REASON_PLAN_CORRUPT]


class TestConsumerWrites:
    def _session(self, observed, rowcounts, verify_rows):
        session = AsyncMock()
        state = {"updates": [], "locks": []}
        calls = iter(rowcounts)

        async def _execute(stmt, params=None):
            sql = str(getattr(stmt, "text", stmt))
            if "pg_advisory_xact_lock" in sql:
                state["locks"].append(params)
                return MagicMock(rowcount=0)
            if sql.strip().startswith("SELECT id, team_id"):
                return _Result([(k, v) for k, v in observed.items()])
            if "UPDATE team_identity_mapping" in sql:
                state["updates"].append(params)
                return MagicMock(rowcount=next(calls))
            if "FROM team_identity_mapping m" in sql:
                return _Result(verify_rows)
            return MagicMock(rowcount=0)

        session.execute = AsyncMock(side_effect=_execute)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session, state

    async def test_it_writes_only_the_approved_rows_with_a_cas(self, monkeypatch):
        import app.tasks.repair_team_identity_mapping as rm

        plan = build_mapping_repair_plan([_row(mapping_id=1), _row(mapping_id=2)])
        monkeypatch.setattr(rm, "_load_plan", AsyncMock(return_value=(plan, "ok")))
        session, state = self._session(
            observed={1: 851, 2: 851},
            rowcounts=[1, 1],
            verify_rows=[
                {"id": 1, "team_id": 867, "source": "polymarket",
                 "sport_key": "baseball_mlb_preseason",
                 "source_name": "San Diego Padres", "club": "San Diego Padres"},
                {"id": 2, "team_id": 867, "source": "polymarket",
                 "sport_key": "baseball_mlb_preseason",
                 "source_name": "San Diego Padres", "club": "San Diego Padres"},
            ],
        )
        out = await rm.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["applied"] is True
        assert out["repointed_count"] == 2
        assert {u["mapping_id"] for u in state["updates"]} == {1, 2}
        # The CAS is carried, not re-read.
        assert all(u["before_team_id"] == 851 for u in state["updates"])
        assert all(u["after_team_id"] == 867 for u in state["updates"])
        assert out["verified"]["at_after"] == 2
        assert out["exhausted"] is True

    async def test_a_row_that_loses_the_cas_retires_and_siblings_continue(self, monkeypatch):
        """``rowcount == 0`` is a finding, never a silent success."""
        import app.tasks.repair_team_identity_mapping as rm

        plan = build_mapping_repair_plan([_row(mapping_id=1), _row(mapping_id=2)])
        monkeypatch.setattr(rm, "_load_plan", AsyncMock(return_value=(plan, "ok")))
        session, state = self._session(
            observed={1: 851, 2: 851},
            rowcounts=[0, 1],   # row 1 rotated between the gate and the update
            verify_rows=[
                {"id": 1, "team_id": 851, "source": "polymarket",
                 "sport_key": "baseball_mlb_preseason",
                 "source_name": "San Diego Padres", "club": "Chicago White Sox"},
                {"id": 2, "team_id": 867, "source": "polymarket",
                 "sport_key": "baseball_mlb_preseason",
                 "source_name": "San Diego Padres", "club": "San Diego Padres"},
            ],
        )
        out = await rm.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["repointed_count"] == 1
        assert [e["mapping_id"] for e in out["lost_cas"]] == [1]
        assert out["lost_cas"][0]["reason_code"] == REASON_MAPPING_BEFORE_DRIFT
        assert out["verified"]["at_after"] == 1
        assert out["verified"]["at_before"] == 1
        assert out["remaining"] == 1
        assert out["exhausted"] is False

    async def test_a_gate_drifted_row_is_never_written(self, monkeypatch):
        import app.tasks.repair_team_identity_mapping as rm

        plan = build_mapping_repair_plan([_row(mapping_id=1), _row(mapping_id=2)])
        monkeypatch.setattr(rm, "_load_plan", AsyncMock(return_value=(plan, "ok")))
        session, state = self._session(
            observed={1: 999, 2: 851},   # row 1 already rotated at gate time
            rowcounts=[1],
            verify_rows=[
                {"id": 1, "team_id": 999, "source": "polymarket",
                 "sport_key": "baseball_mlb_preseason",
                 "source_name": "San Diego Padres", "club": "Someone Else"},
                {"id": 2, "team_id": 867, "source": "polymarket",
                 "sport_key": "baseball_mlb_preseason",
                 "source_name": "San Diego Padres", "club": "San Diego Padres"},
            ],
        )
        out = await rm.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert {u["mapping_id"] for u in state["updates"]} == {2}
        assert [d["mapping_id"] for d in out["gate_drifted"]] == [1]
        # Neither reviewed value -> named, never inferred away.
        assert [e["mapping_id"] for e in out["verified"]["elsewhere"]] == [1]

    async def test_every_write_takes_a_per_mapping_advisory_lock(self, monkeypatch):
        import app.tasks.repair_team_identity_mapping as rm

        plan = build_mapping_repair_plan([_row(mapping_id=1), _row(mapping_id=2)])
        monkeypatch.setattr(rm, "_load_plan", AsyncMock(return_value=(plan, "ok")))
        session, state = self._session(
            observed={1: 851, 2: 851},
            rowcounts=[1, 1],
            verify_rows=[],
        )
        await rm.repair(session, apply=True, plan_hash=plan.plan_hash)
        assert len(state["locks"]) == 2
        assert {l["ns"] for l in state["locks"]} == {rm._ADVISORY_LOCK_NS}
        assert len({l["key"] for l in state["locks"]}) == 2

    async def test_the_cap_is_a_module_constant_not_a_parameter(self):
        import inspect

        import app.tasks.repair_team_identity_mapping as rm

        assert isinstance(rm.APPLY_MAPPING_CAP, int)
        sig = inspect.signature(rm.repair)
        assert set(sig.parameters) == {"session", "apply", "plan_hash"}


class TestConsumerIsRegistered:
    def test_the_dispatcher_knows_the_rail(self):
        """A consumer nobody can invoke is the gap this queue exists to close."""
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["team-identity-mapping-repair"] == (
            "app.tasks.repair_team_identity_mapping",
            "repair",
        )

    def test_the_deriver_and_the_consumer_agree_on_the_schema(self):
        import scripts.derive_mapping_repair_plan as deriver

        assert deriver.SCHEMA == MAPPING_REPAIR_PLAN_SCHEMA

    def test_the_deriver_no_longer_uses_a_raw_join_for_its_digest(self):
        """AST walk, not a text search — ruling 095's companion lesson from q372.

        The first version of this guard was textual and FAILED on its own
        explanatory comment, which quotes ``"|".join`` in order to describe the
        defect. A guard that reads prose cannot tell a warning about a bug from
        the bug. Walk the code.
        """
        import ast
        import inspect
        import textwrap

        import scripts.derive_mapping_repair_plan as deriver

        tree = ast.parse(textwrap.dedent(inspect.getsource(deriver.main)))

        # The digest must be built by the shared encoder...
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "digest_fields"
        ]
        assert calls, "the deriver does not call digest_fields"

        # ...and nowhere in main may a string literal's .join() be used, which is
        # the forgeable encoding. Comments are not in the AST, so the docstring
        # that explains this cannot trip it.
        raw_joins = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "join"
            and isinstance(n.func.value, ast.Constant)
            and isinstance(n.func.value.value, str)
        ]
        assert not raw_joins, (
            "the deriver builds a digest line with a raw string join — the "
            "address is forgeable again"
        )
