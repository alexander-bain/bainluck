"""One explicit recovery step under the local operation hold, never a retry.

Not exposed by the CLI until the operation premises and this implementation are
independently accepted. The caller must satisfy P-EXCL, exact deployed-source
and migration binding, late-command closure and provider qualification. Neither
this API nor verifier output grants those premises. Local tests only so far.
"""

import asyncio
from dataclasses import asdict, dataclass
import json
from uuid import UUID

from app.services.dnpl_activation_command import preview
from app.services.dnpl_authority import Authority
from app.services.dnpl_operation_hold import (
    DeskHold,
    OperationHoldRefused,
    _write_once,
    consume_once,
)
from app.services.dnpl_writer_observations import execute_verifier

STEPS = frozenset(
    {
        "prepare",
        "arm",
        "initialize",
        "ready",
        "retire",
        "acknowledge_retirement",
        "retire_after_primary_change",
        "readback_retirement_after_primary_change",
    }
)


@dataclass(frozen=True)
class StepResult:
    status: str
    step: str
    result: object = None
    error_type: str | None = None


async def run_step(
    *,
    hold: DeskHold,
    controller,
    run_dir,
    run_id: str,
    step: str,
    expected: Authority,
    primary: tuple[str, str],
    apps: dict,
    candidate: Authority | None = None,
) -> StepResult:
    """Directly execute verifier, validate, consume, call controller once, verify.

    No input accepts a completed writer receipt. Every uncertain result ends
    this attempt; callers use the accepted controller's specific readback path.
    The send identity excludes verifier nonce so a newly collected observation
    cannot authorize repeating the same command in this run.
    """
    if step not in STEPS or not isinstance(hold, DeskHold):
        raise OperationHoldRefused("known step and acquired operation hold required")
    UUID(run_id)
    if (step == "prepare") != (candidate is not None):
        raise OperationHoldRefused("only prepare requires an exact retained candidate")
    if candidate is not None and primary != (
        candidate.redis_run_id,
        candidate.redis_master_replid,
    ):
        raise OperationHoldRefused("candidate must bind expected actual primary")
    hold.check()
    before = await asyncio.to_thread(
        execute_verifier,
        run_dir,
        run_id=run_id,
        step=step,
        expected_authority=asdict(expected),
        expected_primary=list(primary),
        apps=apps,
    )
    await preview(controller.store, controller.redis, expected, primary)
    hold.check()
    binding = before.validate()  # freshness measured immediately before send
    identity = {
        "run_id": run_id,
        "step": step,
        "expected": asdict(expected),
        "candidate": None if candidate is None else asdict(candidate),
        "primary": list(primary),
    }
    # UUIDs become canonical strings; latches contain no credentials.
    identity = json.loads(json.dumps(identity, default=str, sort_keys=True))
    latch = consume_once(run_dir, identity)
    # A failed read/write after this point cannot grant another send.
    try:
        hold.check()
        before.validate()  # fsync/check latency cannot extend the freshness bound
        if step == "prepare":
            result = await controller.store.prepare(expected, candidate)
        elif (
            step == "retire_after_primary_change"
            or step == "readback_retirement_after_primary_change"
        ):
            result = await controller.retire_after_primary_change(
                expected,
                redis_run_id=primary[0],
                redis_master_replid=primary[1],
                readback_only=step.startswith("readback_"),
            )
        else:
            result = await getattr(controller, step)(expected)
    except asyncio.CancelledError:
        # The fsynced send latch survives even if cancellation prevents a result.
        raise
    except Exception as exc:
        outcome = StepResult("UNCERTAIN", step, error_type=type(exc).__name__)
    else:
        try:
            hold.check()
            post_expected = result if isinstance(result, Authority) else expected
            after = await asyncio.to_thread(
                execute_verifier,
                run_dir,
                run_id=run_id,
                step=step + ":after",
                expected_authority=asdict(post_expected),
                expected_primary=list(primary),
                apps=apps,
            )
            after.validate()
            hold.check()
            outcome = StepResult(
                "DONE",
                step,
                asdict(result) if isinstance(result, Authority) else result,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outcome = StepResult(
                "UNCERTAIN-WRITER", step, error_type=type(exc).__name__
            )
    record = {
        "outcome": asdict(outcome),
        "send_identity": identity,
        "pre_verifier_nonce": binding["nonce"],
    }
    _write_once(
        run_dir,
        latch.name + ".result",
        json.dumps(record, default=str, sort_keys=True).encode(),
    )
    return outcome
