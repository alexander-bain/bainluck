"""``GET /admin/fold-narrowing-gate/last`` — the way the G1/G3 evidence gets read.

WHY AN ENDPOINT AT ALL. `C-FOLD-REWRITE-1`'s frozen G1 needs OLD and NEW inside
one ``REPEATABLE READ, READ ONLY`` snapshot across at least eight residues, and
G3 needs ``EXPLAIN (ANALYZE, ...)``. Neither fits ``POST /admin/db-query``: its
row path is pinned at a 10 s statement timeout and its ``explain`` never
executes. So the runner is DB-direct on a one-off dyno — and a one-off dyno's
stdout is not evidence in this environment, because ``heroku logs`` is
EPERM-blocked from the agent sandbox and its failure looks exactly like a clean
grep (gotcha #48). The run banks a durable row; this is the reader.

WHAT THESE TESTS PIN, and it is one thing said four ways: **an unmeasured gate
must never read as a passing gate.** The frozen kill criteria make "renders
could-not-check as agreement" an automatic BLOCK, and CAL-P083 already found the
opposite failure once — the twin endpoint discarded a named diagnosis and
answered with the least informative fact available about it. So a torn envelope
stays opaque, an incomplete one surrenders its diagnosis, and neither is ever
``measured: true``.
"""

from __future__ import annotations

import pytest

from app.utils.durable_state import DurableEnvelope, EnvelopeRead

GATE_IDENTITY = "calibration:fold_narrowing_gate"
GATE_SCHEMA = "calibration-fold-narrowing-gate/v1"

#: A run that could not measure: two residues timed out at MOD 64, so no median
#: is available and the artifact banked ``complete=False`` on purpose.
BANKED_UNMEASURED = {
    "cert": "C-FOLD-REWRITE-1",
    "verdict": "NOT_MEASURED",
    "residue_plan_frozen": True,
    "residues_non_adjacent": True,
    "statement_timeout_ms": 300000,
    "one_snapshot": True,
    "g1_required_columns_missing": [],
    "g1": {"verdict": "NOT_MEASURED", "samples": []},
    "g3": {
        "verdict": "NOT_MEASURED",
        "reasons": ["2 of 8 samples did not measure; a median over the survivors is not the gate"],
    },
}

BANKED_PASS = {
    "cert": "C-FOLD-REWRITE-1",
    "verdict": "PASS",
    "one_snapshot": True,
    "g1": {"verdict": "PASS", "samples": []},
    "g3": {"verdict": "PASS", "reasons": []},
}


def _envelope(payload, *, complete: bool):
    return DurableEnvelope.build(
        identity=GATE_IDENTITY,
        schema_version=GATE_SCHEMA,
        payload=payload,
        complete=complete,
        source="scripts/verify_fold_narrowing_row_identity.py",
    )


async def _call(monkeypatch, read: EnvelopeRead):
    from app.routes import admin_cohort

    monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)

    async def _fake_read(identity, *, expected_version=None, max_age_s=None):
        assert identity == GATE_IDENTITY, "writer and reader disagree on the identity"
        assert expected_version == GATE_SCHEMA
        return read

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
    return await admin_cohort.fold_narrowing_gate_last(request=None)


class TestTheRouteIsReachable:
    def test_it_is_registered_on_the_mounted_router(self):
        # Admin endpoints have to be mounted to exist (gotcha #2). This router
        # is already mounted, so registration is the whole check — but a typo in
        # the path is otherwise invisible until an operator curls it.
        from app.main import app

        paths = {r.path for r in app.routes}
        assert "/api/admin/fold-narrowing-gate/last" in paths

    @pytest.mark.asyncio
    async def test_it_is_admin_gated(self, monkeypatch):
        from app.routes import admin_cohort

        calls = []
        monkeypatch.setattr(
            admin_cohort, "_check_admin_secret", lambda **kw: calls.append(kw)
        )

        async def _fake_read(identity, **kw):
            return EnvelopeRead(status="missing", tier="durable", envelope=None,
                                error_class=None, error=None)

        import app.services.durable_snapshots as ds

        monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
        await admin_cohort.fold_narrowing_gate_last(request=None)
        assert calls, "the reader answered without checking the admin secret"


class TestAnUnmeasuredRunNeverReadsAsAgreement:
    @pytest.mark.asyncio
    async def test_an_incomplete_artifact_surrenders_its_diagnosis(self, monkeypatch):
        read = EnvelopeRead(
            status="malformed",
            tier="durable",
            envelope=_envelope(BANKED_UNMEASURED, complete=False),
            error_class="IncompleteArtifact",
            error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)

        assert out["measured"] is False
        assert out["failed_run"]["g3_verdict"] == "NOT_MEASURED"
        assert "median over the survivors" in out["failed_run"]["g3_reasons"][0]
        assert out["failed_run"]["one_snapshot"] is True

    @pytest.mark.asyncio
    async def test_the_verdict_is_not_promoted_to_the_top_level(self, monkeypatch):
        """The one shape this endpoint must never produce.

        ``verdict`` lives inside ``failed_run`` where a caller has to go looking
        for it, and ``measured`` is False beside it. A tool keying on the
        response's top level cannot mistake a timed-out gate for a green one.
        """
        read = EnvelopeRead(
            status="malformed",
            tier="durable",
            envelope=_envelope(BANKED_UNMEASURED, complete=False),
            error_class="IncompleteArtifact",
            error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)
        assert "verdict" not in out
        assert out["failed_run"]["verdict"] == "NOT_MEASURED"

    @pytest.mark.asyncio
    async def test_a_torn_envelope_stays_opaque(self, monkeypatch):
        """Bytes that fail their own checksum cannot describe themselves.

        Recovering a diagnosis from them would be strictly worse than the bare
        status: it would be a confident sentence sourced from data we have just
        proved untrustworthy.
        """
        read = EnvelopeRead(
            status="malformed",
            tier="durable",
            envelope=None,
            error_class="ChecksumMismatch",
            error="checksum does not match payload",
        )
        out = await _call(monkeypatch, read)
        assert out["measured"] is False
        assert out["envelope_error_class"] == "ChecksumMismatch"
        assert "failed_run" not in out

    @pytest.mark.asyncio
    async def test_a_missing_row_is_named_not_zeroed(self, monkeypatch):
        read = EnvelopeRead(
            status="missing", tier="durable", envelope=None,
            error_class=None, error=None,
        )
        out = await _call(monkeypatch, read)
        assert out["measured"] is False
        assert out["reason"] == "artifact_unreadable: missing"

    @pytest.mark.asyncio
    async def test_a_raising_reader_is_an_answer_not_a_500(self, monkeypatch):
        from app.routes import admin_cohort

        monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)

        async def _boom(identity, **kw):
            raise RuntimeError("durable store unreachable")

        import app.services.durable_snapshots as ds

        monkeypatch.setattr(ds, "read_snapshot_standalone", _boom)
        out = await admin_cohort.fold_narrowing_gate_last(request=None)
        assert out["measured"] is False
        assert "RuntimeError" in out["reason"]


class TestACompleteRunIsServed:
    @pytest.mark.asyncio
    async def test_a_pass_is_measured_and_stamped(self, monkeypatch):
        env = _envelope(BANKED_PASS, complete=True)
        read = EnvelopeRead(status="ok", tier="durable", envelope=env,
                            error_class=None, error=None)
        out = await _call(monkeypatch, read)
        assert out["measured"] is True
        assert out["verdict"] == "PASS"
        assert out["artifact_generated_at"] == env.generated_at.isoformat()


class TestTheRunnerAndTheReaderAgree:
    def test_the_identity_and_schema_constants_match(self):
        """A writer and a reader that disagree bank into a hole.

        The runner is a script rather than an importable module by design (it
        runs on a dyno with no app context beyond ``sys.path``), so the constants
        are read out of its source rather than imported — which is exactly the
        drift this test exists to catch.
        """
        import pathlib
        import re

        source = (
            pathlib.Path(__file__).parents[1]
            / "scripts"
            / "verify_fold_narrowing_row_identity.py"
        ).read_text()
        identity = re.search(r'GATE_IDENTITY = "([^"]+)"', source).group(1)
        schema = re.search(r'GATE_SCHEMA = "([^"]+)"', source).group(1)
        assert identity == GATE_IDENTITY
        assert schema == GATE_SCHEMA

        reader = (
            pathlib.Path(__file__).parents[1] / "app" / "routes" / "admin_cohort.py"
        ).read_text()
        assert f'identity = "{GATE_IDENTITY}"' in reader
        assert f'schema = "{GATE_SCHEMA}"' in reader


# ---------------------------------------------------------------------------
# CAL-P101 — ``projection_delta``: the column-set half of G3
# ---------------------------------------------------------------------------


class TestProjectionDelta:
    """The byte total and the column set answer different questions.

    G3.2's ``Plan Width`` ratio is an estimate built from ``pg_statistic``; on
    an unANALYZEd seed every column is priced by ``get_typavgwidth`` instead.
    Membership of ``Output`` is not an estimate, so it is gradeable anywhere —
    and it is the rewrite's actual structural claim. These tests pin the
    reader; the CI gate applies it to a real plan.
    """

    @staticmethod
    def _mets(cols):
        return {"sort_output": list(cols), "sort_output_n": len(cols)}

    def test_the_deferred_relations_leave_and_the_base_columns_stay(self):
        from app.utils.fold_narrowing_gate import projection_delta

        out = projection_delta(
            self._mets(["fo.id", "fo.name", "cv.source", "mb.win_count", "mfd.cp_sum"]),
            self._mets(["fo.id", "fo.name", "cv.source"]),
        )

        assert out["measured"] is True
        assert out["dropped"] == ["mb.win_count", "mfd.cp_sum"]
        assert out["dropped_n"] == 2
        assert out["retained_n"] == 3
        assert out["added"] == []
        assert out["deferred_alias_survivors"] == []

    def test_a_surviving_deferred_column_is_named_not_just_counted(self):
        """The whole point: a partial defer must not read as a defer.

        Eight of nine relations leaving and one staying still shrinks the byte
        total, still shrinks the column count, and still leaves the window
        computed over a nine-way join. Only the alias check catches it.
        """
        from app.utils.fold_narrowing_gate import projection_delta

        out = projection_delta(
            self._mets(["fo.id", "mb.win_count", "gpm.market_id"]),
            self._mets(["fo.id", "gpm.market_id"]),
        )

        assert out["dropped_n"] == 1
        assert out["deferred_alias_survivors"] == ["gpm.market_id"]

    def test_an_identical_projection_reports_an_empty_delta(self):
        from app.utils.fold_narrowing_gate import projection_delta

        out = projection_delta(self._mets(["fo.id"]), self._mets(["fo.id"]))

        assert out["measured"] is True
        assert out["dropped_n"] == 0
        assert out["deferred_alias_survivors"] == []

    @pytest.mark.parametrize(
        "old_cols,new_cols,missing",
        [
            ([], ["fo.id"], "old"),
            (["fo.id"], [], "new"),
            ([], [], "old/new"),
        ],
    )
    def test_a_missing_output_list_is_not_measured(self, old_cols, new_cols, missing):
        """``EXPLAIN`` without ``VERBOSE`` omits ``Output`` entirely.

        An absent column list read as "no columns survived" would be a perfect
        score from a statement that was never asked the question — this gate's
        own version of the empty 200 (gotcha #53).
        """
        from app.utils.fold_narrowing_gate import projection_delta

        out = projection_delta(self._mets(old_cols), self._mets(new_cols))

        assert out["measured"] is False
        assert missing in out["reason"]
        assert "dropped_n" not in out

    def test_every_deferred_alias_in_the_sql_is_declared_to_the_reader(self):
        """The alias list is a copy of the SQL, so it can rot silently.

        A LEFT JOIN renamed in ``precompute_calibration.py`` and not here would
        make ``deferred_alias_survivors`` blind to exactly the relation that
        moved — the check would keep returning ``[]`` and mean nothing.
        """
        import pathlib
        import re

        from app.utils.fold_narrowing_gate import DEFERRED_JOIN_ALIASES

        source = (
            pathlib.Path(__file__).parents[1]
            / "app"
            / "tasks"
            / "precompute_calibration.py"
        ).read_text()
        block = source.split("ranked_outcomes AS MATERIALIZED (", 1)[1]
        block = block.split("\n            ),", 1)[0]
        aliases = set(
            re.findall(r"LEFT JOIN\s+\w+\s+(\w+)\s+ON\s+\1\.market_id", block)
        )

        assert aliases, "no LEFT JOIN aliases found — the SQL shape moved"
        assert aliases == set(DEFERRED_JOIN_ALIASES), (
            "the deferred-join alias list and the SQL disagree: "
            f"sql-only={sorted(aliases - set(DEFERRED_JOIN_ALIASES))} "
            f"reader-only={sorted(set(DEFERRED_JOIN_ALIASES) - aliases)}"
        )
