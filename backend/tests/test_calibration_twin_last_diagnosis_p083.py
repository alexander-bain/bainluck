"""``GET /admin/calibration-twin/last`` must surface a FAILED run — CAL-P083.

The twin worker is careful. It refuses to let a fold that errored, a payload it
could not read, or a fold that returned zero rows present as agreement; it types
each by name and banks the artifact with ``complete=False`` so the envelope layer
can never SERVE a non-verdict as a verdict. All of that is right and none of it
is changed here.

What was wrong is that the one endpoint whose job is to explain a failed gate run
answered ``{"measured": false, "reason": "artifact_unreadable: malformed"}`` over
a 195 KB artifact reading, in full, *"QueryCanceledError: canceling statement due
to statement timeout"* after 241.18 s against a 240 s budget. The names were
written and then discarded at the last hop — gotcha #53's shape occurring inside
the instrument built to avoid it, which is why it survived three queues.

So this suite pins the distinction the fix rests on, in both directions:

* an INCOMPLETE envelope is recoverable — it is a real artifact that declined to
  be a verdict, and its diagnosis is the whole point of asking;
* a CHECKSUM-TORN or MISSING envelope is NOT — bytes that fail their own checksum
  cannot be trusted to describe themselves, and inventing a diagnosis from them
  would be strictly worse than the bare status.

And in every case ``measured`` stays ``False``. The failure mode this must never
enable is a caller reading ``verdict`` off a recovered artifact and treating a
timed-out fold as an agreement.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.durable_state import DurableEnvelope, EnvelopeRead

TWIN_SCHEMA = "calibration-published-twin/v1"
TWIN_IDENTITY = "calibration:published_twin"

#: The production artifact of 2026-08-21 14:03:02Z, reduced to the fields the
#: endpoint recovers. The fold ran its entire budget and was cancelled.
BANKED_FAILURE = {
    "queue": "CAL-P080",
    "verdict": "unmeasurable",
    "unmeasurable_reason": (
        "DBAPIError: (sqlalchemy.dialects.postgresql.asyncpg.Error) "
        "<class 'asyncpg.exceptions.QueryCanceledError'>: canceling statement "
        "due to statement timeout"
    ),
    "fold_error": (
        "QueryCanceledError: canceling statement due to statement timeout"
    ),
    "payload_error": None,
    "fold_duration_s": 241.18,
    "timeout_ms": 240000,
    "db_rows": 0,
    "db_cells": 0,
    "terminal": "failed",
    "tolerance_pp": None,
    "published_generated_at": None,
    "published_availability": None,
    # Present in the real artifact and deliberately NOT recovered: the endpoint
    # returns a fixed diagnostic field list, not the whole 195 KB body.
    "gate": "Gate 0 — bounded agreement, published curve vs DB-direct (in-dyno)",
}


def _envelope(payload, *, complete=False):
    return DurableEnvelope.build(
        identity=TWIN_IDENTITY,
        schema_version=TWIN_SCHEMA,
        payload=payload,
        complete=complete,
        source="calibration_published_twin",
    )


async def _call(monkeypatch, read: EnvelopeRead):
    """Invoke the endpoint with the envelope read stubbed."""
    from app.routes import admin_cohort

    monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)

    async def _fake_read(identity, *, expected_version=None, max_age_s=None):
        assert identity == TWIN_IDENTITY
        assert expected_version == TWIN_SCHEMA
        return read

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
    return await admin_cohort.calibration_twin_last(request=None)


class TestAnIncompleteArtifactIsRecovered:
    @pytest.mark.asyncio
    async def test_the_timeout_reason_reaches_the_operator(self, monkeypatch):
        env = _envelope(BANKED_FAILURE)
        read = EnvelopeRead(
            status="malformed", tier="durable", envelope=env,
            error_class="IncompleteArtifact",
            error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)

        assert out["measured"] is False
        assert "QueryCanceledError" in out["failed_run"]["unmeasurable_reason"]

    @pytest.mark.asyncio
    async def test_the_budget_overrun_is_visible_as_two_numbers(self, monkeypatch):
        """241.18 s against 240,000 ms is the finding.

        Either number alone is unremarkable; the pair is what says the fold did
        not fail early, it consumed its whole budget and was cut off.
        """
        env = _envelope(BANKED_FAILURE)
        read = EnvelopeRead(
            status="malformed", tier="durable", envelope=env,
            error_class="IncompleteArtifact", error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)
        assert out["failed_run"]["fold_duration_s"] == 241.18
        assert out["failed_run"]["timeout_ms"] == 240000

    @pytest.mark.asyncio
    async def test_zero_rows_is_reported_not_smoothed(self, monkeypatch):
        env = _envelope(BANKED_FAILURE)
        read = EnvelopeRead(
            status="malformed", tier="durable", envelope=env,
            error_class="IncompleteArtifact", error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)
        assert out["failed_run"]["db_rows"] == 0
        assert out["failed_run"]["db_cells"] == 0

    @pytest.mark.asyncio
    async def test_the_envelope_error_class_distinguishes_incomplete_from_torn(
        self, monkeypatch
    ):
        env = _envelope(BANKED_FAILURE)
        read = EnvelopeRead(
            status="malformed", tier="durable", envelope=env,
            error_class="IncompleteArtifact", error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)
        assert out["envelope_error_class"] == "IncompleteArtifact"

    @pytest.mark.asyncio
    async def test_recovery_never_promotes_the_run_to_measured(self, monkeypatch):
        """The failure this fix must not enable.

        ``verdict: "unmeasurable"`` is inside ``failed_run`` where a caller has
        to go looking for it. It is NOT lifted to the top level, and ``measured``
        is False, so a timed-out fold cannot be mistaken for an agreement by
        anything reading the response shape.
        """
        env = _envelope(BANKED_FAILURE)
        read = EnvelopeRead(
            status="malformed", tier="durable", envelope=env,
            error_class="IncompleteArtifact", error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)
        assert out["measured"] is False
        assert "verdict" not in out
        assert out["failed_run"]["verdict"] == "unmeasurable"

    @pytest.mark.asyncio
    async def test_only_the_named_diagnostic_fields_are_returned(self, monkeypatch):
        """The artifact is 195 KB; this endpoint is not a dump.

        ``gate`` is in the banked payload and must not come back — the recovery
        is a fixed field list so the response cannot grow a whole fold's worth
        of buckets the day someone banks one.
        """
        env = _envelope(BANKED_FAILURE)
        read = EnvelopeRead(
            status="malformed", tier="durable", envelope=env,
            error_class="IncompleteArtifact", error="envelope is marked incomplete",
        )
        out = await _call(monkeypatch, read)
        assert "gate" not in out["failed_run"]


class TestUntrustworthyBytesAreNotMined:
    @pytest.mark.asyncio
    async def test_a_missing_row_recovers_nothing(self, monkeypatch):
        read = EnvelopeRead(status="missing", tier="durable")
        out = await _call(monkeypatch, read)
        assert out["measured"] is False
        assert "failed_run" not in out

    @pytest.mark.asyncio
    async def test_a_checksum_mismatch_recovers_nothing(self, monkeypatch):
        """Malformed, but with no envelope — the bytes failed their own checksum.

        Same ``status`` as the incomplete case, opposite handling. A torn write
        may parse perfectly, which is exactly why the checksum exists, so any
        diagnosis mined from it would be fiction presented as evidence.
        """
        read = EnvelopeRead(
            status="malformed", tier="durable", envelope=None,
            error_class="ChecksumMismatch",
            error="payload checksum does not match the stored envelope",
        )
        out = await _call(monkeypatch, read)
        assert out["measured"] is False
        assert "failed_run" not in out
        assert out["envelope_error_class"] == "ChecksumMismatch"

    @pytest.mark.asyncio
    async def test_a_wrong_version_row_is_not_mined(self, monkeypatch):
        """Deploy skew, not corruption — and its fields may mean something else.

        The envelope IS carried on a version mismatch, so this is the case where
        recovery would silently succeed against a schema nobody checked.
        """
        env = _envelope(BANKED_FAILURE)
        read = EnvelopeRead(
            status="wrong_version", tier="durable", envelope=env,
            error_class="VersionMismatch", error="schema_version mismatch",
        )
        out = await _call(monkeypatch, read)
        assert out["measured"] is False
        assert "failed_run" not in out


class TestASuccessfulReadIsUnchanged:
    @pytest.mark.asyncio
    async def test_a_complete_artifact_returns_the_whole_payload(self, monkeypatch):
        good = {"verdict": "agrees", "measured": True, "tolerance_pp": 0.5,
                "compared": 1934, "outside": []}
        env = _envelope(good, complete=True)
        read = EnvelopeRead(status="ok", tier="durable", envelope=env)
        out = await _call(monkeypatch, read)
        assert out["verdict"] == "agrees"
        assert out["tolerance_pp"] == 0.5
        assert "artifact_generated_at" in out
        assert "failed_run" not in out
