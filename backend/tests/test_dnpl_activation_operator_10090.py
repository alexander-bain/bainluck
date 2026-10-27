"""Command wiring preserves the reviewed runner, hold and refusal boundaries."""

import asyncio
from dataclasses import asdict
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.services import dnpl_activation_operator as operator
from app.services.dnpl_activation_runner import StepResult
from app.services.dnpl_authority import Authority, preparing_candidate
from app.services.dnpl_operation_hold import OperationHoldRefused


def plan_data():
    authority = Authority(3, 1, uuid4(), uuid4(), "preparing", "a" * 40, "b" * 40, "p")
    expected = json.loads(json.dumps(asdict(authority), default=str))
    return {
        "run_id": str(uuid4()),
        "primary": "a" * 40 + ":" + "b" * 40,
        "apps": {
            app: {"release": 1, "slug": str(uuid4()), "commit": "c" * 40}
            for app in operator.APPS
        },
        "steps": [
            {"step": step, "expected": expected.copy(), "candidate": None}
            for step in ("arm", "initialize", "ready")
        ],
    }


def parse(data):
    return operator.parse_plan(json.dumps(data).encode())


def test_valid_plan_keeps_exact_targets_and_no_permission_field():
    data = plan_data()
    plan = parse(data)
    assert plan.run_id == data["run_id"]
    assert plan.primary == ("a" * 40, "b" * 40)
    assert [item.step for item in plan.steps] == ["arm", "initialize", "ready"]
    assert json.loads(plan.encoded) == data


@pytest.mark.parametrize(
    "defect",
    [
        "extra",
        "duplicate",
        "empty",
        "large",
        "unknown",
        "candidate",
        "discontinuous",
        "repeat",
        "apps",
        "diverged",
        "release",
        "slug",
        "commit",
        "zero_run",
    ],
)
def test_entire_plan_is_validated_before_execution(defect):
    data = plan_data()
    if defect == "extra":
        data["writers_stopped"] = True
    elif defect == "duplicate":
        encoded = json.dumps(data)[:-1] + ', "run_id": "' + data["run_id"] + '"}'
        with pytest.raises(ValueError):
            operator.parse_plan(encoded.encode())
        return
    elif defect == "empty":
        data["steps"] = []
    elif defect == "large":
        data["steps"] *= 3
    elif defect == "unknown":
        data["steps"][-1]["step"] = "flush"
    elif defect == "candidate":
        data["steps"][-1]["candidate"] = data["steps"][-1]["expected"]
    elif defect == "discontinuous":
        data["steps"][-1]["expected"]["incarnation"] = 2
    elif defect == "repeat":
        data["steps"].append(data["steps"][0])
    elif defect == "apps":
        data["apps"]["unexpected-app"] = data["apps"][operator.APPS[0]]
    elif defect == "diverged":
        data["apps"][operator.APPS[0]]["commit"] = "d" * 40
    elif defect == "zero_run":
        data["run_id"] = "00000000-0000-0000-0000-000000000000"
    else:
        data["apps"][operator.APPS[0]][defect] = {
            "release": True,
            "slug": "bad",
            "commit": "HEAD",
        }[defect]
    with pytest.raises((ValueError, TypeError)):
        parse(data)


def test_plan_input_is_private_owned_regular_and_bounded(tmp_path):
    source = tmp_path / "plan"
    source.write_bytes(json.dumps(plan_data()).encode())
    source.chmod(0o600)
    assert operator.read_plan(source).steps
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(OSError):
        operator.read_plan(link)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(ValueError):
        operator.read_plan(fifo)
    source.chmod(0o644)
    with pytest.raises(ValueError):
        operator.read_plan(source)
    source.chmod(0o600)
    source.write_bytes(b" " * (operator.MAX_PLAN_BYTES + 1))
    with pytest.raises(ValueError):
        operator.read_plan(source)


@pytest.fixture
def local_run(tmp_path):
    lock = tmp_path / "lane.lock"
    lock.write_text(
        f"status: HELD\nowner_identity: local-operator-test\nowner_pid: {os.getpid()}\nclaimed_epoch_s: 1\n"
    )
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    return {"lock_path": lock, "identity": "local-operator-test", "run_dir": run}


@pytest.mark.parametrize("outcome", ["DONE", "UNCERTAIN", "UNCERTAIN-WRITER"])
async def test_one_continuous_hold_and_stop_on_uncertainty(
    local_run, monkeypatch, outcome
):
    plan = parse(plan_data())
    calls = []

    async def step(**kwargs):
        kwargs["hold"].check()
        calls.append(kwargs)
        return StepResult(
            outcome if kwargs["step"] == "initialize" else "DONE", kwargs["step"]
        )

    monkeypatch.setattr(operator, "run_step", step)
    controller = SimpleNamespace(read_ready=AsyncMock(return_value=True))
    result = await operator.execute_plan(plan, controller, **local_run)
    assert len({id(call["hold"]) for call in calls}) == 1
    assert [call["step"] for call in calls] == (
        ["arm", "initialize", "ready"] if outcome == "DONE" else ["arm", "initialize"]
    )
    assert result["status"] == ("PLAN_DONE" if outcome == "DONE" else outcome)
    assert (local_run["run_dir"] / "plan.json").read_bytes() == plan.encoded
    with pytest.raises(OperationHoldRefused, match="not acquired"):
        calls[0]["hold"].check()
    # Rerunning the directory cannot recreate the plan or invoke another send.
    with pytest.raises(OperationHoldRefused, match="already consumed"):
        await operator.execute_plan(plan, controller, **local_run)


async def test_ready_readback_false_is_not_plan_success(local_run, monkeypatch):
    monkeypatch.setattr(
        operator, "run_step", AsyncMock(return_value=StepResult("DONE", "ready"))
    )
    result = await operator.execute_plan(
        parse(plan_data()),
        SimpleNamespace(read_ready=AsyncMock(return_value=False)),
        **local_run,
    )
    assert result["status"] == "UNCERTAIN"
    assert result["ready_readback"] is False


async def test_lost_hold_between_steps_prevents_next_send(local_run, monkeypatch):
    calls = []

    async def step(**kwargs):
        kwargs["hold"].check()
        calls.append(kwargs["step"])
        local_run["lock_path"].write_text("status: FREE\n")
        return StepResult("DONE", kwargs["step"])

    monkeypatch.setattr(operator, "run_step", step)
    with pytest.raises(OperationHoldRefused):
        await operator.execute_plan(parse(plan_data()), object(), **local_run)
    assert calls == ["arm"]


def test_cli_invalid_late_step_never_configures_clients(tmp_path, monkeypatch, capsys):
    data = plan_data()
    data["steps"][-1]["step"] = "bad"
    source = tmp_path / "plan"
    source.write_text(json.dumps(data))
    source.chmod(0o600)
    configured = AsyncMock()
    monkeypatch.setattr(operator, "configured_plan", configured)
    assert (
        operator.main(
            [
                "execute-plan",
                "--plan",
                str(source),
                "--lock",
                "/unused",
                "--owner",
                "unused",
                "--run-dir",
                str(tmp_path),
            ]
        )
        == 2
    )
    configured.assert_not_awaited()
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"


def test_late_exception_is_uncertain_and_credential_safe(tmp_path, monkeypatch, capsys):
    source = tmp_path / "plan"
    source.write_text(json.dumps(plan_data()))
    source.chmod(0o600)
    monkeypatch.setattr(
        operator,
        "configured_plan",
        AsyncMock(side_effect=ConnectionError("redis://secret-password@host")),
    )
    assert (
        operator.main(
            [
                "execute-plan",
                "--plan",
                str(source),
                "--lock",
                "/unused",
                "--owner",
                "unused",
                "--run-dir",
                str(tmp_path),
            ]
        )
        == 3
    )
    output = capsys.readouterr().out
    assert "secret-password" not in output
    assert json.loads(output)["status"] == "STOPPED"
    assert json.loads(output)["may_have_sent"] is True


async def test_application_credentials_are_never_fallback(monkeypatch):
    monkeypatch.delenv("DNPL_COMMAND_DATABASE_URL", raising=False)
    monkeypatch.delenv("DNPL_COMMAND_REDIS_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("REDIS_URL", "redis://unused")
    import sqlalchemy.ext.asyncio as sa

    factory = AsyncMock()
    monkeypatch.setattr(sa, "create_async_engine", factory)
    with pytest.raises(KeyError):
        await operator.configured_plan(parse(plan_data()))
    factory.assert_not_called()


@pytest.mark.parametrize("io_ms", [150, 1000])
async def test_explicit_connections_are_bounded_and_cleaned(monkeypatch, io_ms):
    from unittest.mock import Mock
    import redis.asyncio as redis
    import sqlalchemy.ext.asyncio as sa
    from sqlalchemy.pool import NullPool

    monkeypatch.setenv(
        "DNPL_COMMAND_DATABASE_URL", "postgresql://user:password@localhost/test"
    )
    monkeypatch.setenv("DNPL_COMMAND_REDIS_URL", "redis://localhost:1/0")
    engine = SimpleNamespace(dispose=AsyncMock())
    factory = Mock(return_value=engine)
    client = SimpleNamespace(aclose=AsyncMock())
    redis_factory = Mock(return_value=client)
    monkeypatch.setattr(sa, "create_async_engine", factory)
    monkeypatch.setattr(redis.Redis, "from_url", redis_factory)
    monkeypatch.setattr(
        operator, "execute_plan", AsyncMock(side_effect=RuntimeError("stop"))
    )
    with pytest.raises(RuntimeError):
        await operator.configured_plan(
            parse(plan_data()), budgets=operator.OperatorBudgets(io_ms, 5000)
        )
    assert factory.call_args.kwargs["poolclass"] is NullPool
    assert factory.call_args.kwargs["connect_args"]["server_settings"] == {
        "statement_timeout": "150",
        "lock_timeout": "150",
    }
    assert redis_factory.call_args.kwargs["socket_timeout"] == io_ms / 1000
    assert redis_factory.call_args.kwargs["socket_connect_timeout"] == io_ms / 1000
    assert redis_factory.call_args.kwargs["retry"].get_retries() == 0
    client.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_cancellation_keeps_plan_and_releases_hold(local_run, monkeypatch):
    holds = []

    async def cancel(**kwargs):
        holds.append(kwargs["hold"])
        raise asyncio.CancelledError()

    monkeypatch.setattr(operator, "run_step", cancel)
    with pytest.raises(asyncio.CancelledError):
        await operator.execute_plan(parse(plan_data()), object(), **local_run)
    assert (local_run["run_dir"] / "plan.json").exists()
    with pytest.raises(OperationHoldRefused, match="not acquired"):
        holds[0].check()


def lifecycle_plan(sequence):
    data = plan_data()
    current = Authority(3, 0, UUID(int=0), UUID(int=0), "disabled", "", "", "")
    data["steps"] = []
    for step in sequence:
        candidate = (
            preparing_candidate(
                current,
                namespace=uuid4(),
                operation_id=uuid4(),
                redis_run_id="a" * 40,
                redis_master_replid="b" * 40,
                policy_fingerprint="p",
            )
            if step == "prepare"
            else None
        )
        data["steps"].append(
            {
                "step": step,
                "expected": asdict(current),
                "candidate": None if candidate is None else asdict(candidate),
            }
        )
        if candidate is not None:
            current = candidate
        elif step == "ready":
            from dataclasses import replace

            current = replace(current, state="ready")
    return json.loads(json.dumps(data, default=str))


@pytest.mark.parametrize(
    "sequence",
    [
        ("prepare", "prepare", "arm"),
        ("prepare", "initialize"),
        ("prepare", "ready"),
        ("prepare", "arm", "ready"),
        ("prepare", "arm", "initialize", "prepare"),
        ("prepare", "arm", "retire"),
        ("prepare", "arm", "initialize", "ready", "initialize"),
    ],
)
def test_impossible_lifecycle_is_refused_before_clients(
    sequence, tmp_path, monkeypatch, capsys
):
    source = tmp_path / "plan"
    source.write_text(json.dumps(lifecycle_plan(sequence)))
    source.chmod(0o600)
    configured = AsyncMock()
    monkeypatch.setattr(operator, "configured_plan", configured)
    assert (
        operator.main(
            [
                "execute-plan",
                "--plan",
                str(source),
                "--lock",
                "/unused",
                "--owner",
                "unused",
                "--run-dir",
                str(tmp_path),
            ]
        )
        == 2
    )
    configured.assert_not_awaited()
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"
    assert not (tmp_path / "plan.json").exists()


@pytest.mark.parametrize(
    "steps",
    [
        ("initialize", "ready"),
        ("ready",),
        ("retire",),
        ("acknowledge_retirement",),
        ("arm", "retire", "initialize", "ready"),
    ],
)
def test_existing_authority_partial_and_readback_plans_remain_valid(steps):
    data = plan_data()
    expected = data["steps"][0]["expected"]
    data["steps"] = [
        {"step": step, "expected": expected.copy(), "candidate": None} for step in steps
    ]
    assert len(parse(data).steps) == len(steps)


@pytest.mark.parametrize(
    "step", ["retire_after_primary_change", "readback_retirement_after_primary_change"]
)
def test_replacement_cleanup_plan_retains_distinct_primary_requirement(step):
    data = plan_data()
    data["steps"] = [
        {"step": step, "expected": data["steps"][0]["expected"], "candidate": None}
    ]
    with pytest.raises(ValueError, match="primary"):
        parse(data)
    data["primary"] = "d" * 40 + ":" + "e" * 40
    assert parse(data).steps[0].step == step


async def test_effective_budget_receipt_and_runner_selection_are_retained(
    local_run, monkeypatch
):
    from app.services.dnpl_operator_budget import OperatorBudgets

    budgets = OperatorBudgets(1000, 5000)
    calls = []

    async def step(**kwargs):
        calls.append(kwargs)
        return StepResult("UNCERTAIN", kwargs["step"])

    monkeypatch.setattr(operator, "run_step", step)
    result = await operator.execute_plan(
        parse(plan_data()), object(), budgets=budgets, **local_run
    )
    assert result["transport_budgets"] == {"io_ms": 1000, "preview_ms": 5000}
    assert (
        json.loads((local_run["run_dir"] / "transport-budgets.json").read_text())
        == result["transport_budgets"]
    )
    assert calls[0]["preview_budget_s"] == 5
    with pytest.raises(OperationHoldRefused, match="already consumed"):
        await operator.execute_plan(
            parse(plan_data()),
            object(),
            budgets=OperatorBudgets(5000, 30000),
            **local_run,
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "io,preview", [("5001", "30000"), ("1000", "999"), ("0", "1000")]
)
def test_cli_budget_refuses_before_clients(tmp_path, monkeypatch, io, preview):
    configured = AsyncMock()
    monkeypatch.setattr(operator, "configured_plan", configured)
    assert (
        operator.main(
            [
                "execute-plan",
                "--plan",
                str(tmp_path / "absent"),
                "--lock",
                "/unused",
                "--owner",
                "unused",
                "--run-dir",
                str(tmp_path),
                "--io-budget-ms",
                io,
                "--preview-budget-ms",
                preview,
            ]
        )
        == 2
    )
    configured.assert_not_awaited()
