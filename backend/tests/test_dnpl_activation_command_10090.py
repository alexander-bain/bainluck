"""The command preview cannot become a writer-stop or activation receipt."""

import asyncio
from dataclasses import asdict, replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.services import dnpl_activation_command as command
from app.services.dnpl_authority import Authority, AuthorityConflict


@pytest.fixture
def subject():
    expected = Authority(
        3, 1, UUID(int=1), UUID(int=2), "preparing", "a" * 40, "b" * 40, "p"
    )
    store = SimpleNamespace(
        read=AsyncMock(return_value=expected),
        activation_step=AsyncMock(return_value=2),
        read_retirement=AsyncMock(return_value=None),
    )
    redis = SimpleNamespace(
        info=AsyncMock(
            return_value={
                "role": "master",
                "run_id": "a" * 40,
                "master_replid": "b" * 40,
            }
        )
    )
    return expected, store, redis


async def test_preview_reports_exact_snapshot_without_permission(subject):
    expected, store, redis = subject
    result = await command.preview(store, redis, expected, ("a" * 40, "b" * 40))
    assert result["status"] == "SNAPSHOT_MATCH"
    assert result["mutation_permitted"] is False
    assert result["interlock"] == "UNIMPLEMENTED"
    assert result["activation_step"] == 2
    redis.info.assert_awaited_once_with("all")
    assert store.read.await_count == 2


@pytest.mark.parametrize("changed", ["authority", "step", "retirement"])
async def test_changed_sample_refuses(subject, changed):
    expected, store, redis = subject
    if changed == "authority":
        store.read.side_effect = [expected, replace(expected, state="ready")]
    elif changed == "step":
        store.activation_step.side_effect = [1, 2]
    else:
        store.read_retirement.side_effect = [expected, None]
    with pytest.raises(AuthorityConflict, match="changed during preview"):
        await command.preview(store, redis, expected, ("a" * 40, "b" * 40))


async def test_stale_expected_authority_does_not_contact_redis(subject):
    expected, store, redis = subject
    with pytest.raises(AuthorityConflict, match="expected authority differs"):
        await command.preview(
            store, redis, replace(expected, state="ready"), ("a" * 40, "b" * 40)
        )
    redis.info.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value",
    [("role", "slave"), ("run_id", "c" * 40), ("master_replid", "d" * 40)],
)
async def test_wrong_primary_refuses(subject, field, value):
    expected, store, redis = subject
    redis.info.return_value[field] = value
    with pytest.raises(AuthorityConflict, match="expected Redis primary differs"):
        await command.preview(store, redis, expected, ("a" * 40, "b" * 40))


async def test_lost_read_reply_is_not_retried(subject):
    expected, store, redis = subject
    redis.info.side_effect = TimeoutError
    with pytest.raises(TimeoutError):
        await command.preview(store, redis, expected, ("a" * 40, "b" * 40))
    redis.info.assert_awaited_once()


async def test_total_budget_is_bounded(subject, monkeypatch):
    expected, store, redis = subject

    async def never(*args):
        await asyncio.Event().wait()

    redis.info.side_effect = never
    monkeypatch.setattr(command, "READ_BUDGET_S", 0.01)
    with pytest.raises(TimeoutError):
        await command.preview(store, redis, expected, ("a" * 40, "b" * 40))
    redis.info.assert_awaited_once()


def test_strict_comparison_input(subject):
    expected, _, _ = subject
    encoded = json.dumps(asdict(expected), default=str)
    assert command.parse_authority(encoded) == expected
    with pytest.raises(ValueError, match="duplicate"):
        command.parse_authority(encoded[:-1] + ', "protocol": 3}')
    with pytest.raises(ValueError, match="exact authority"):
        command.parse_authority(encoded[:-1] + ', "writers_stopped": true}')
    with pytest.raises(ValueError):
        command.parse_primary("a" * 40 + ":" + "b" * 40 + "\n")


def test_no_mutating_subcommand_or_receipt_override():
    for operation in ("prepare", "arm", "initialize", "ready", "retire"):
        with pytest.raises(SystemExit) as error:
            command.main([operation])
        assert error.value.code == 2


def test_connection_failure_does_not_print_credentials(subject, monkeypatch, capsys):
    expected, _, _ = subject
    monkeypatch.setattr(
        command,
        "_configured_preview",
        AsyncMock(side_effect=RuntimeError("redis://secret@private")),
    )
    assert (
        command.main(
            [
                "preview",
                "--expected-authority",
                json.dumps(asdict(expected), default=str),
                "--expected-primary",
                "a" * 40 + ":" + "b" * 40,
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out) == {
        "status": "REFUSED",
        "error_type": "RuntimeError",
    }


async def test_explicit_preview_total_still_bounds_all_reads(subject):
    expected, store, redis = subject

    async def blocked(*a):
        await asyncio.Event().wait()

    redis.info.side_effect = blocked
    with pytest.raises(TimeoutError):
        await command.preview(
            store, redis, expected, ("a" * 40, "b" * 40), budget_s=0.01
        )
    redis.info.assert_awaited_once()
