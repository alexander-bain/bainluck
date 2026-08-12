"""CAL-P048 (#1768) — a successful durable-baseline recovery must be visible.

C-RV-3 certified CAL-P042 GREEN with one nonblocking finding, and this is it.
``PublishVerdict`` learned ``baseline_source`` and ``baseline_probe`` so that
``found`` / ``cold_start`` / ``indeterminate`` could be told apart — but the
publisher copied neither into the ``gate`` summary nor into ``runner.outcome``.
The consequence is asymmetric and easy to miss:

* A **rejected** build was already diagnosable. Its codes, detail and probe
  status ride into the deduped issue, so ``baseline_unreadable`` announces
  itself.
* A **successful** build that recovered its baseline from durable history was
  byte-identical, in every terminal artifact, to one that read Redis normally.

So the one path the branch was written to expose — the safety net actually
catching something and the build going on to publish — was the one path that
left no trace. That is the observability twin of gotcha #53: two different
facts collapsing into one reading, except here the collapse is on the success
side, where nobody is looking.

THE DISCRIMINATION TEST IS THE POINT. ``test_volatile_and_durable_passes_are_..``
runs two builds that differ ONLY in which store answered, deliberately using the
SAME prior payload as both the volatile value and the durable one so every other
gate field is identical by construction. It then asserts that the two summaries
differ in EXACTLY the two new keys. Delete either key from the packet and that
test fails on the "differ" half; leak any other difference into the fixture and
it fails on the "identical otherwise" half. A per-field ``== "durable"`` assert
alone would pass against a packet that could not distinguish anything.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.tasks.precompute_calibration as pc
from app.tasks.precompute_calibration import (
    _MAIN_KEY,
    _precompute_calibration_main,
)
from app.utils.calibration_durable_baseline import (
    COLD_START,
    FOUND,
    INDETERMINATE,
    BaselineProbe,
)

# Offset FIRST, then truncate (gotcha #44). A fixed hour would make the payload's
# age swing a full day with the wall clock; this holds a constant 48h.
_GENERATED_AT = (
    (datetime.now(timezone.utc) - timedelta(days=2))
    .replace(minute=0, second=0, microsecond=0)
    .isoformat()
)


def _payload(outcomes: int = 635_464) -> dict:
    """A structurally complete, gate-passable payload."""
    return {
        "buckets": [{"bucket": i} for i in range(12)],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "by_category": [{"category": "politics", "outcomes": outcomes}],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "generated_at": _GENERATED_AT,
    }


class _FakeCM:
    def __init__(self):
        self.db = AsyncMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *a):
        return False


async def _run_beat(*, volatile: dict | None, probe: BaselineProbe):
    """Run one publish beat and return ``(summary_or_error, ledger_outcome)``.

    ``ledger_outcome`` is the ``outcome`` dict as ``save_phase_ledger`` actually
    received it — the durable run evidence, not a local copy of it. Captured
    through the real call so a change that updates the summary and forgets the
    ledger (or vice versa) cannot pass.
    """
    rc = MagicMock()
    rc.get.side_effect = lambda key: (
        json.dumps(volatile) if (volatile is not None and key == _MAIN_KEY) else None
    )
    candidate = _payload()

    captured: dict = {}

    async def _capture_ledger(runner, extra):
        captured.update(extra)
        return "ok"

    async def _compute(db, **_kwargs):
        return candidate

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM()), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(pc, "compute_calibration_payload", _compute), patch(
        "app.utils.calibration_durable_baseline.probe_durable_baseline",
        lambda *a, **k: probe,
    ), patch(
        "app.tasks.calibration_main_build.save_phase_ledger", _capture_ledger
    ):
        try:
            summary = await _precompute_calibration_main()
        except Exception as exc:  # noqa: BLE001 — the refusal path is under test
            summary = exc

    return summary, captured.get("outcome", {})


async def test_volatile_baseline_pass_reports_provided_and_no_probe():
    """The ordinary case: Redis answered, so no probe was needed or claimed."""
    summary, outcome = await _run_beat(volatile=_payload(), probe=BaselineProbe(COLD_START))

    assert summary["status"] == "ok"
    assert summary["gate"]["ok"] is True
    assert summary["gate"]["baseline_source"] == "provided"
    # None, not "cold_start": the probe fixture above would have answered
    # cold_start if it had been consulted, and a usable volatile baseline must
    # not consult it. This asserts the probe did NOT run, which a truthy
    # placeholder would hide.
    assert summary["gate"]["baseline_probe"] is None
    assert outcome["baseline_source"] == "provided"
    assert outcome["baseline_probe"] is None


async def test_durable_recovery_pass_is_recorded_as_durable_found():
    """The invisible case: the safety path fired and the build still published."""
    prior = _payload()
    summary, outcome = await _run_beat(
        volatile=None,
        probe=BaselineProbe(FOUND, payload=prior, detail="recovered generation 41"),
    )

    assert summary["status"] == "ok"
    assert summary["gate"]["ok"] is True
    # It published WITHOUT first-publish semantics — it had a real baseline to
    # compare against, recovered from durable history.
    assert summary["gate"]["first_publish"] is False
    assert summary["gate"]["baseline_source"] == "durable"
    assert summary["gate"]["baseline_probe"] == FOUND
    assert outcome["baseline_source"] == "durable"
    assert outcome["baseline_probe"] == FOUND


async def test_proved_cold_start_pass_is_recorded_as_none_cold_start():
    summary, outcome = await _run_beat(
        volatile=None, probe=BaselineProbe(COLD_START, detail="no durable row")
    )

    assert summary["status"] == "ok"
    assert summary["gate"]["first_publish"] is True
    assert summary["gate"]["baseline_source"] == "none"
    assert summary["gate"]["baseline_probe"] == COLD_START
    assert outcome["baseline_source"] == "none"
    assert outcome["baseline_probe"] == COLD_START


async def test_volatile_and_durable_passes_are_distinguishable_and_only_there():
    """Two successful publishes, same numbers, different store — and it shows.

    The negative control is the second assertion: with the two new keys removed,
    the packets are EQUAL. That is what made this a defect rather than a
    nice-to-have — the terminal record of a durable recovery was a byte-for-byte
    match for an ordinary beat, so no amount of reading the logs could find one.
    """
    prior = _payload()

    volatile_summary, _ = await _run_beat(volatile=prior, probe=BaselineProbe(COLD_START))
    durable_summary, _ = await _run_beat(
        volatile=None, probe=BaselineProbe(FOUND, payload=prior)
    )

    a = dict(volatile_summary["gate"])
    b = dict(durable_summary["gate"])

    differing = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert differing == {"baseline_source", "baseline_probe"}, (
        "the two builds must differ in exactly the provenance fields; "
        f"got {sorted(differing)}"
    )

    for key in ("baseline_source", "baseline_probe"):
        a.pop(key)
        b.pop(key)
    assert a == b


async def test_refused_build_still_records_which_baseline_refused_it():
    """Provenance is written BEFORE the rejection branch, so a refusal keeps it.

    ``baseline_unreadable`` raises out of the build. If the two assignments sat
    after that branch, the one terminal that most needs to name its baseline
    would be the one without it.
    """
    summary, outcome = await _run_beat(
        volatile=None,
        probe=BaselineProbe(
            INDETERMINATE, detail="durable store unavailable", envelope_status="unavailable"
        ),
    )

    assert isinstance(summary, Exception)
    assert "baseline_unreadable" in str(summary)
    assert outcome["gate"] == "refuse"
    assert outcome["baseline_source"] == "unknown"
    assert outcome["baseline_probe"] == INDETERMINATE


@pytest.mark.parametrize("field", ["baseline_source", "baseline_probe"])
def test_the_verdict_still_carries_both_fields(field):
    """A shape guard: the packet copies fields that exist on the verdict.

    Renaming one on ``PublishVerdict`` without updating the publisher would
    otherwise surface as an ``AttributeError`` deep inside a beat rather than
    here.
    """
    from app.utils.calibration_publish_gate import PublishVerdict

    assert hasattr(PublishVerdict(ok=True), field)
