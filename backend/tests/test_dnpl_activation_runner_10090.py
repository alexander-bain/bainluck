"""Single-send wrapper controls with real local operation locks and no network."""

from dataclasses import replace
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import dnpl_activation_runner as runner
from app.services.dnpl_authority import Authority
from app.services.dnpl_operation_hold import DeskHold, OperationHoldRefused


@pytest.fixture
def operation(tmp_path, monkeypatch):
    started = subprocess.check_output(
        ["ps", "-p", str(os.getpid()), "-o", "lstart="], text=True
    ).strip()
    lock = tmp_path / "lane.lock"
    lock.write_text(
        f"status: HELD\nowner_identity: integrator-local-test\nowner_pid: {os.getpid()}\nclaimed_epoch_s: 1\n"
    )
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    authority = Authority(3, 1, uuid4(), uuid4(), "preparing", "a" * 40, "b" * 40, "p")
    controller = SimpleNamespace(
        store=SimpleNamespace(prepare=AsyncMock()),
        redis=object(),
        arm=AsyncMock(),
        initialize=AsyncMock(),
        ready=AsyncMock(return_value=replace(authority, state="ready")),
    )
    captures = []

    def verifier(*args, **kwargs):
        captures.append(kwargs["step"])
        return SimpleNamespace(validate=lambda: {"nonce": str(uuid4())})

    monkeypatch.setattr(runner, "execute_verifier", verifier)
    monkeypatch.setattr(runner, "preview", AsyncMock())
    return SimpleNamespace(
        hold=DeskHold(lock, "integrator-local-test", os.getpid(), started, 1),
        controller=controller,
        run_dir=run,
        run_id=str(uuid4()),
        expected=authority,
        primary=("a" * 40, "b" * 40),
        apps={},
        captures=captures,
    )


def args(operation, step):
    return {
        key: getattr(operation, key)
        for key in (
            "hold",
            "controller",
            "run_dir",
            "run_id",
            "expected",
            "primary",
            "apps",
        )
    } | {"step": step}


async def test_missing_hold_sends_nothing(operation):
    with pytest.raises(OperationHoldRefused, match="not acquired"):
        await runner.run_step(**args(operation, "arm"))
    assert operation.captures == []
    operation.controller.arm.assert_not_awaited()


async def test_success_has_pre_and_post_verification_and_no_second_send(operation):
    with operation.hold.held():
        assert (await runner.run_step(**args(operation, "arm"))).status == "DONE"
        with pytest.raises(OperationHoldRefused, match="already consumed"):
            await runner.run_step(**args(operation, "arm"))
    operation.controller.arm.assert_awaited_once()
    assert operation.captures[:2] == ["arm", "arm:after"]


async def test_lost_reply_retains_uncertainty_and_no_replay(operation):
    operation.controller.initialize.side_effect = ConnectionError("lost reply")
    with operation.hold.held():
        result = await runner.run_step(**args(operation, "initialize"))
        assert result.status == "UNCERTAIN"
        assert result.error_type == "ConnectionError"
        with pytest.raises(OperationHoldRefused, match="already consumed"):
            await runner.run_step(**args(operation, "initialize"))
    operation.controller.initialize.assert_awaited_once()


async def test_post_send_writer_does_not_report_done(operation, monkeypatch):
    def verifier(*args, **kwargs):
        if kwargs["step"].endswith(":after"):
            raise OperationHoldRefused("writer appeared")
        return SimpleNamespace(validate=lambda: {"nonce": "pre"})

    monkeypatch.setattr(runner, "execute_verifier", verifier)
    with operation.hold.held():
        result = await runner.run_step(**args(operation, "arm"))
    assert result.status == "UNCERTAIN-WRITER"
    operation.controller.arm.assert_awaited_once()


async def test_permission_fsync_delay_cannot_extend_freshness(operation, monkeypatch):
    checks = []

    def validate():
        checks.append(1)
        if len(checks) == 2:
            raise OperationHoldRefused("stale after permission fsync")
        return {"nonce": "pre"}

    monkeypatch.setattr(
        runner, "execute_verifier", lambda *a, **k: SimpleNamespace(validate=validate)
    )
    with operation.hold.held():
        result = await runner.run_step(**args(operation, "arm"))
    assert result.status == "UNCERTAIN"
    operation.controller.arm.assert_not_awaited()
    assert list(operation.run_dir.glob("*.send-consumed"))


async def test_prepare_requires_retained_candidate_bound_to_primary(operation):
    with operation.hold.held():
        with pytest.raises(OperationHoldRefused, match="retained candidate"):
            await runner.run_step(**args(operation, "prepare"))
        with pytest.raises(OperationHoldRefused, match="actual primary"):
            await runner.run_step(
                **args(operation, "prepare"),
                candidate=replace(operation.expected, redis_run_id="c" * 40),
            )
    operation.controller.store.prepare.assert_not_awaited()


async def test_larger_preview_budget_never_changes_send_identity(operation):
    with operation.hold.held():
        assert (
            await runner.run_step(**args(operation, "arm"), preview_budget_s=5)
        ).status == "DONE"
        with pytest.raises(OperationHoldRefused, match="already consumed"):
            await runner.run_step(**args(operation, "arm"), preview_budget_s=30)
    operation.controller.arm.assert_awaited_once()


async def test_longer_preview_does_not_extend_writer_freshness(operation, monkeypatch):
    expired = False

    async def preview(*a, **k):
        nonlocal expired
        assert k["budget_s"] == 30
        expired = True

    def validate():
        if expired:
            raise OperationHoldRefused("collection stale")
        return {"nonce": "before"}

    monkeypatch.setattr(runner, "preview", preview)
    monkeypatch.setattr(
        runner, "execute_verifier", lambda *a, **k: SimpleNamespace(validate=validate)
    )
    with operation.hold.held(), pytest.raises(OperationHoldRefused, match="stale"):
        await runner.run_step(**args(operation, "arm"), preview_budget_s=30)
    operation.controller.arm.assert_not_awaited()
    assert not list(operation.run_dir.glob("*.send-consumed"))
