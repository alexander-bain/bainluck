"""CAL-P042 (#1768): durable history is the publish gate's third place to look.

The defect these encode: an absent baseline and a never-existed baseline
returned the SAME answer, and the gate inferred the emptier reading. Every test
here is about keeping those two apart, so the decision table is exercised
directly rather than only through the gate.

The single most important assertion in the file is
``test_the_probe_reads_without_the_serving_age_cutoff``. ``SERVE_MAX_AGE_S``
expiring is what created #1768 in the first place; a probe that inherited the
default age bound would expire its answer during exactly the long outage it
exists to detect, and we would have rebuilt the bug one layer down with a
passing test suite on top of it.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import calibration_durable_baseline as cdb
from app.utils.durable_state import DurableEnvelope, EnvelopeRead

PAYLOAD = {"total_outcomes": 652_407, "population_version": "q267"}


def _envelope(payload=PAYLOAD, *, age_days: float = 30.0) -> DurableEnvelope:
    return DurableEnvelope.build(
        identity=cdb.DURABLE_IDENTITY,
        schema_version="q267",
        payload=payload,
        generated_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        source="precompute_calibration",
    )


def _read(status: str, *, envelope=None, error=None) -> EnvelopeRead:
    return EnvelopeRead(status=status, tier="durable", envelope=envelope, error=error)


# ---------------------------------------------------------------------------
# The decision table
# ---------------------------------------------------------------------------


def test_a_readable_prior_generation_is_found():
    probe = cdb.probe_durable_baseline(reader=lambda: _read("ok", envelope=_envelope()))

    assert probe.status == cdb.FOUND
    assert probe.payload == PAYLOAD
    assert probe.generated_at is not None


def test_an_absent_row_is_the_only_proved_cold_start():
    probe = cdb.probe_durable_baseline(reader=lambda: _read("missing"))

    assert probe.status == cdb.COLD_START


@pytest.mark.parametrize(
    "status",
    ["unavailable", "malformed", "wrong_type", "wrong_version", "stale"],
)
def test_every_other_classified_read_is_indeterminate(status):
    """None of these prove absence, so none of them may be read as one."""
    probe = cdb.probe_durable_baseline(
        reader=lambda: _read(status, error="something went wrong")
    )

    assert probe.status == cdb.INDETERMINATE
    assert probe.envelope_status == status
    assert status in probe.detail


def test_an_ok_row_whose_payload_is_not_an_object_is_indeterminate():
    """It decoded, so a prior generation exists — it just cannot be compared."""
    probe = cdb.probe_durable_baseline(
        reader=lambda: _read("ok", envelope=_envelope(payload=["not", "a", "dict"]))
    )

    assert probe.status == cdb.INDETERMINATE
    assert probe.payload is None


def test_a_raising_reader_is_indeterminate_not_a_cold_start():
    def boom():
        raise RuntimeError("connection refused")

    probe = cdb.probe_durable_baseline(reader=boom)

    assert probe.status == cdb.INDETERMINATE
    assert "RuntimeError" in probe.detail


def test_a_timeout_is_indeterminate_not_a_cold_start():
    def slow():
        raise concurrent.futures.TimeoutError()

    probe = cdb.probe_durable_baseline(reader=slow)

    assert probe.status == cdb.INDETERMINATE
    assert "timed out" in probe.detail


def test_an_unrecognised_status_falls_to_indeterminate():
    """Fail closed on a status this module has never heard of."""
    probe = cdb.probe_durable_baseline(reader=lambda: _read("some_future_status"))

    assert probe.status == cdb.INDETERMINATE


def test_a_reader_returning_none_is_indeterminate():
    probe = cdb.probe_durable_baseline(reader=lambda: None)

    assert probe.status == cdb.INDETERMINATE


# ---------------------------------------------------------------------------
# The two properties that make the probe correct rather than merely present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_probe_reads_without_the_serving_age_cutoff(monkeypatch):
    """An artifact too old to SERVE is still proof a prior generation existed.

    Guarded explicitly because inheriting ``DEFAULT_MAX_AGE_S`` would reproduce
    #1768 inside its own fix: the durable answer would expire during the same
    long outage that expired the Redis keys.
    """
    seen = {}

    async def fake_read(identity, *, expected_version=None, max_age_s=None):
        seen["identity"] = identity
        seen["max_age_s"] = max_age_s
        seen["expected_version"] = expected_version
        return _read("ok", envelope=_envelope(age_days=400))

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", fake_read)

    result = await cdb._read_durable_envelope()

    assert seen["identity"] == "calibration:main"
    assert seen["max_age_s"] == float("inf")
    # No expected_version: a version CHANGE is the gate's own `version_bumped`
    # decision to make, not a reason to refuse to read the prior generation.
    assert seen["expected_version"] is None
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_the_probe_works_from_inside_a_running_event_loop(monkeypatch):
    """`evaluate_publish` is sync and is called from an async publisher.

    Neither `await` nor `asyncio.run` is available at that call site, so the
    probe bridges through a worker thread with its own loop. If that bridge is
    wrong the whole fix is inert in production while every injected-reader test
    above still passes — so it is proved here against the real, unpatched
    threading path.
    """
    async def fake_read(identity, *, expected_version=None, max_age_s=None):
        await asyncio.sleep(0)  # a real await, on the probe's own loop
        return _read("ok", envelope=_envelope())

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", fake_read)

    assert asyncio.get_running_loop().is_running()
    probe = cdb.probe_durable_baseline()  # no reader: the real threaded bridge

    assert probe.status == cdb.FOUND
    assert probe.payload == PAYLOAD


@pytest.mark.asyncio
async def test_a_hung_durable_read_is_bounded_and_does_not_deadlock(monkeypatch):
    """A wedged store costs one bounded probe, never the beat's window."""
    async def hangs(identity, *, expected_version=None, max_age_s=None):
        await asyncio.sleep(30)
        raise AssertionError("should never be reached")

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", hangs)

    probe = cdb.probe_durable_baseline(timeout_s=0.25)

    assert probe.status == cdb.INDETERMINATE
    assert "timed out" in probe.detail
